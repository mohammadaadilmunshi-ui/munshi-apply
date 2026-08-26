import { and, eq, gt, isNull } from "drizzle-orm";
import { getDb } from "../../../db";
import { pairingChallenges } from "../../../db/schema";
import {
  apiError,
  authError,
  getOrCreateOwnerWorkspace,
  randomSecret,
  sha256Hex,
} from "../_shared";

const PAIRING_LIFETIME_MILLISECONDS = 10 * 60 * 1_000;

export async function POST() {
  try {
    const workspace = await getOrCreateOwnerWorkspace();
    const secret = randomSecret();
    const now = new Date();
    const challenge = {
      id: crypto.randomUUID(),
      workspaceId: workspace.id,
      secretSha256: await sha256Hex(secret),
      expiresAt: new Date(
        now.getTime() + PAIRING_LIFETIME_MILLISECONDS,
      ).toISOString(),
    };
    await getDb().insert(pairingChallenges).values(challenge);

    return Response.json(
      {
        challenge: {
          id: challenge.id,
          secret,
          expiresAt: challenge.expiresAt,
        },
      },
      { status: 201 },
    );
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}

export async function GET() {
  try {
    const workspace = await getOrCreateOwnerWorkspace();
    const now = new Date().toISOString();
    const challenges = await getDb()
      .select({
        id: pairingChallenges.id,
        expiresAt: pairingChallenges.expiresAt,
        createdAt: pairingChallenges.createdAt,
      })
      .from(pairingChallenges)
      .where(
        and(
          eq(pairingChallenges.workspaceId, workspace.id),
          isNull(pairingChallenges.usedAt),
          gt(pairingChallenges.expiresAt, now),
        ),
      )
      .limit(5);
    return Response.json({ challenges });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
