import { and, eq, gt, isNull } from "drizzle-orm";
import { getDb } from "../../../db";
import { devices, pairingChallenges } from "../../../db/schema";
import { apiError, authError, requirePrincipal, sha256Hex } from "../_shared";

type ActivationPayload = {
  challengeId?: string;
  secret?: string;
};

export async function POST(request: Request) {
  try {
    const principal = await requirePrincipal(request);
    if (principal.kind !== "device" || !principal.deviceId) {
      return Response.json(
        { error: "A paired Edge installation is required." },
        { status: 403 },
      );
    }

    const payload = (await request.json()) as ActivationPayload;
    const challengeId = payload.challengeId?.trim() ?? "";
    const secret = payload.secret?.trim() ?? "";
    if (!challengeId || secret.length < 32) {
      return Response.json(
        { error: "Invalid encryption activation request." },
        { status: 400 },
      );
    }

    const challenge = await getDb().query.pairingChallenges.findFirst({
      where: and(
        eq(pairingChallenges.id, challengeId),
        eq(pairingChallenges.workspaceId, principal.workspaceId),
      ),
    });
    const now = new Date().toISOString();
    if (
      !challenge ||
      challenge.usedAt ||
      challenge.expiresAt <= now ||
      challenge.secretSha256 !== (await sha256Hex(secret))
    ) {
      return Response.json(
        { error: "Encryption activation code is invalid or expired." },
        { status: 410 },
      );
    }

    const database = getDb();
    const activated = await database
      .update(pairingChallenges)
      .set({ usedAt: now })
      .where(
        and(
          eq(pairingChallenges.id, challengeId),
          eq(pairingChallenges.workspaceId, principal.workspaceId),
          isNull(pairingChallenges.usedAt),
          gt(pairingChallenges.expiresAt, now),
        ),
      )
      .returning({ id: pairingChallenges.id });
    if (activated.length !== 1) {
      return Response.json(
        { error: "Encryption activation code was already used." },
        { status: 409 },
      );
    }
    await database
      .update(devices)
      .set({ lastSeenAt: now })
      .where(eq(devices.id, principal.deviceId));

    return Response.json({ encryption: { status: "ACTIVE", version: 1 } });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
