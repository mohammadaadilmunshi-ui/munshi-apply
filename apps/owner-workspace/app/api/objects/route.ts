import { env } from "cloudflare:workers";
import { desc, eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { encryptedObjects } from "../../../db/schema";
import { apiError, authError, requirePrincipal, sha256Hex } from "../_shared";

const MAX_ENCRYPTED_OBJECT_BYTES = 20 * 1024 * 1024;
const safeId = /^[a-zA-Z0-9_-]{8,128}$/;

export async function GET(request: Request) {
  try {
    const principal = await requirePrincipal(request);
    const objects = await getDb()
      .select({
        id: encryptedObjects.id,
        purpose: encryptedObjects.purpose,
        metadataCiphertext: encryptedObjects.metadataCiphertext,
        wrappedKey: encryptedObjects.wrappedKey,
        payloadSha256: encryptedObjects.payloadSha256,
        sizeBytes: encryptedObjects.sizeBytes,
        createdAt: encryptedObjects.createdAt,
      })
      .from(encryptedObjects)
      .where(eq(encryptedObjects.workspaceId, principal.workspaceId))
      .orderBy(desc(encryptedObjects.createdAt))
      .limit(100);
    return Response.json({ objects });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}

export async function POST(request: Request) {
  let uploadedKey: string | null = null;
  try {
    const principal = await requirePrincipal(request);
    if (request.headers.get("content-type") !== "application/octet-stream") {
      return Response.json(
        { error: "Encrypted uploads require application/octet-stream." },
        { status: 415 },
      );
    }

    const objectId = request.headers.get("x-munshi-object-id")?.trim() ?? "";
    const purpose = request.headers.get("x-munshi-purpose")?.trim() ?? "";
    const metadataCiphertext =
      request.headers.get("x-munshi-metadata-ciphertext")?.trim() ?? "";
    const wrappedKey =
      request.headers.get("x-munshi-wrapped-key")?.trim() ?? "";
    const claimedSha256 =
      request.headers.get("x-munshi-payload-sha256")?.trim().toLowerCase() ??
      "";

    if (
      !safeId.test(objectId) ||
      !["RESUME", "EVIDENCE", "EXPORT", "BACKUP"].includes(purpose) ||
      !metadataCiphertext ||
      metadataCiphertext.length > 12_000 ||
      !wrappedKey ||
      wrappedKey.length > 12_000 ||
      !/^[a-f0-9]{64}$/.test(claimedSha256)
    ) {
      return Response.json(
        { error: "Encrypted object metadata is invalid." },
        { status: 400 },
      );
    }

    const existing = await getDb().query.encryptedObjects.findFirst({
      where: eq(encryptedObjects.id, objectId),
    });
    if (existing) {
      if (
        existing.workspaceId === principal.workspaceId &&
        existing.payloadSha256 === claimedSha256
      ) {
        return Response.json({ object: { id: objectId }, duplicate: true });
      }
      return Response.json({ error: "Object ID conflict." }, { status: 409 });
    }

    const body = await request.arrayBuffer();
    if (body.byteLength === 0 || body.byteLength > MAX_ENCRYPTED_OBJECT_BYTES) {
      return Response.json(
        { error: "Encrypted object size is invalid." },
        { status: 413 },
      );
    }
    const actualSha256 = await sha256Hex(body);
    if (actualSha256 !== claimedSha256) {
      return Response.json(
        { error: "Encrypted object checksum mismatch." },
        { status: 422 },
      );
    }

    uploadedKey = `${principal.workspaceId}/${objectId}`;
    await env.BUCKET.put(uploadedKey, body, {
      httpMetadata: { contentType: "application/octet-stream" },
      customMetadata: { payloadSha256: actualSha256, purpose },
    });
    await getDb().insert(encryptedObjects).values({
      id: objectId,
      workspaceId: principal.workspaceId,
      objectKey: uploadedKey,
      purpose,
      metadataCiphertext,
      wrappedKey,
      payloadSha256: actualSha256,
      sizeBytes: body.byteLength,
    });
    return Response.json(
      { object: { id: objectId, payloadSha256: actualSha256 } },
      { status: 201 },
    );
  } catch (error) {
    if (uploadedKey)
      await env.BUCKET.delete(uploadedKey).catch(() => undefined);
    return authError(error) ?? apiError(error);
  }
}
