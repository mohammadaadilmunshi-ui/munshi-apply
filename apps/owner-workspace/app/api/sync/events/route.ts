import { env } from "cloudflare:workers";
import { and, asc, eq, gt } from "drizzle-orm";
import { getDb } from "../../../../db";
import { conflicts, entityVersions, syncEvents } from "../../../../db/schema";
import {
  apiError,
  authError,
  requirePrincipal,
  sha256Hex,
} from "../../_shared";

type SyncPayload = {
  id?: string;
  correlationId?: string;
  entityType?: string;
  entityId?: string;
  baseVersion?: number;
  schemaVersion?: string;
  payloadCiphertext?: string;
  payloadSha256?: string;
};

const safeIdentifier = /^[a-zA-Z0-9_.:-]{8,160}$/;

async function recordConflict(
  workspaceId: string,
  payload: Required<SyncPayload>,
  expectedVersion: number,
) {
  const conflictId = crypto.randomUUID();
  await getDb()
    .insert(conflicts)
    .values({
      id: conflictId,
      workspaceId,
      entityType: payload.entityType,
      entityId: payload.entityId,
      incomingEventId: payload.id,
      correlationId: payload.correlationId,
      schemaVersion: payload.schemaVersion,
      payloadCiphertext: payload.payloadCiphertext,
      payloadSha256: payload.payloadSha256,
      expectedVersion,
      receivedBaseVersion: payload.baseVersion,
    })
    .onConflictDoNothing();
  const recorded = await getDb().query.conflicts.findFirst({
    where: eq(conflicts.incomingEventId, payload.id),
  });
  return recorded?.id ?? conflictId;
}

export async function GET(request: Request) {
  try {
    const principal = await requirePrincipal(request);
    const cursorValue = new URL(request.url).searchParams.get("cursor") ?? "0";
    const cursor = Number(cursorValue);
    if (!Number.isSafeInteger(cursor) || cursor < 0) {
      return Response.json({ error: "Invalid sync cursor." }, { status: 400 });
    }
    const events = await getDb()
      .select({
        sequence: syncEvents.sequence,
        id: syncEvents.id,
        deviceId: syncEvents.deviceId,
        correlationId: syncEvents.correlationId,
        entityType: syncEvents.entityType,
        entityId: syncEvents.entityId,
        baseVersion: syncEvents.baseVersion,
        schemaVersion: syncEvents.schemaVersion,
        payloadCiphertext: syncEvents.payloadCiphertext,
        payloadSha256: syncEvents.payloadSha256,
        createdAt: syncEvents.createdAt,
      })
      .from(syncEvents)
      .where(
        and(
          eq(syncEvents.workspaceId, principal.workspaceId),
          gt(syncEvents.sequence, cursor),
        ),
      )
      .orderBy(asc(syncEvents.sequence))
      .limit(250);
    return Response.json({
      events,
      nextCursor: events.at(-1)?.sequence ?? cursor,
      hasMore: events.length === 250,
    });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}

export async function POST(request: Request) {
  try {
    const principal = await requirePrincipal(request);
    const candidate = (await request.json()) as SyncPayload;
    const payload = {
      id: candidate.id?.trim() ?? "",
      correlationId: candidate.correlationId?.trim() ?? "",
      entityType: candidate.entityType?.trim() ?? "",
      entityId: candidate.entityId?.trim() ?? "",
      baseVersion: candidate.baseVersion ?? -1,
      schemaVersion: candidate.schemaVersion?.trim() ?? "",
      payloadCiphertext: candidate.payloadCiphertext?.trim() ?? "",
      payloadSha256: candidate.payloadSha256?.trim().toLowerCase() ?? "",
    } satisfies Required<SyncPayload>;

    if (
      !safeIdentifier.test(payload.id) ||
      !safeIdentifier.test(payload.correlationId) ||
      !safeIdentifier.test(payload.entityType) ||
      !safeIdentifier.test(payload.entityId) ||
      !Number.isSafeInteger(payload.baseVersion) ||
      payload.baseVersion < 0 ||
      !/^\d+\.\d+$/.test(payload.schemaVersion) ||
      !payload.payloadCiphertext ||
      payload.payloadCiphertext.length > 350_000 ||
      !/^[a-f0-9]{64}$/.test(payload.payloadSha256) ||
      (await sha256Hex(payload.payloadCiphertext)) !== payload.payloadSha256
    ) {
      return Response.json({ error: "Invalid sync event." }, { status: 400 });
    }

    const existing = await getDb().query.syncEvents.findFirst({
      where: eq(syncEvents.id, payload.id),
    });
    if (existing) {
      if (
        existing.workspaceId === principal.workspaceId &&
        existing.payloadSha256 === payload.payloadSha256
      ) {
        return Response.json({ event: { id: payload.id }, duplicate: true });
      }
      return Response.json({ error: "Event ID conflict." }, { status: 409 });
    }

    const version = await getDb().query.entityVersions.findFirst({
      where: and(
        eq(entityVersions.workspaceId, principal.workspaceId),
        eq(entityVersions.entityType, payload.entityType),
        eq(entityVersions.entityId, payload.entityId),
      ),
    });
    const expectedVersion = version?.currentVersion ?? 0;
    if (payload.baseVersion !== expectedVersion) {
      const conflictId = await recordConflict(
        principal.workspaceId,
        payload,
        expectedVersion,
      );
      return Response.json(
        { conflict: { id: conflictId, expectedVersion } },
        { status: 409 },
      );
    }

    const nextVersion = expectedVersion + 1;
    try {
      await env.DB.batch([
        env.DB.prepare(
          `INSERT INTO sync_events (
            id, workspace_id, device_id, correlation_id, entity_type, entity_id,
            base_version, schema_version, payload_ciphertext, payload_sha256
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        ).bind(
          payload.id,
          principal.workspaceId,
          principal.deviceId,
          payload.correlationId,
          payload.entityType,
          payload.entityId,
          payload.baseVersion,
          payload.schemaVersion,
          payload.payloadCiphertext,
          payload.payloadSha256,
        ),
        env.DB.prepare(
          `INSERT INTO entity_versions (
            workspace_id, entity_type, entity_id, current_version, last_event_id
          ) VALUES (?, ?, ?, ?, ?)
          ON CONFLICT(workspace_id, entity_type, entity_id)
          DO UPDATE SET current_version = excluded.current_version,
            last_event_id = excluded.last_event_id,
            updated_at = CURRENT_TIMESTAMP`,
        ).bind(
          principal.workspaceId,
          payload.entityType,
          payload.entityId,
          nextVersion,
          payload.id,
        ),
      ]);
    } catch {
      const latest = await getDb().query.entityVersions.findFirst({
        where: and(
          eq(entityVersions.workspaceId, principal.workspaceId),
          eq(entityVersions.entityType, payload.entityType),
          eq(entityVersions.entityId, payload.entityId),
        ),
      });
      const conflictId = await recordConflict(
        principal.workspaceId,
        payload,
        latest?.currentVersion ?? expectedVersion,
      );
      return Response.json(
        {
          conflict: {
            id: conflictId,
            expectedVersion: latest?.currentVersion ?? expectedVersion,
          },
        },
        { status: 409 },
      );
    }

    return Response.json(
      { event: { id: payload.id, version: nextVersion } },
      { status: 201 },
    );
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
