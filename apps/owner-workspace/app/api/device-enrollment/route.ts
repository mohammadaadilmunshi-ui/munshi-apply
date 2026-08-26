import { env } from "cloudflare:workers";
import { eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { pairingChallenges } from "../../../db/schema";
import { apiError, randomSecret, sha256Hex } from "../_shared";

type EnrollmentPayload = {
  challengeId?: string;
  secret?: string;
  deviceId?: string;
  labelCiphertext?: string;
  platform?: string;
  publicKeyJwk?: JsonWebKey;
  signature?: string;
};

const platformAliases = new Map([
  ["android", "android"],
  ["cros", "chromeos"],
  ["ios", "ios"],
  ["linux", "linux"],
  ["mac", "macos"],
  ["macos", "macos"],
  ["openbsd", "openbsd"],
  ["win", "windows"],
  ["windows", "windows"],
]);

function normalizePlatform(value: string | undefined): string {
  return platformAliases.get(value?.trim().toLowerCase() ?? "") ?? "";
}

function decodeBase64Url(value: string): ArrayBuffer {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const decoded = atob(padded);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index);
  }
  return bytes.buffer;
}

async function verifyEnrollmentProof(
  payload: Required<
    Pick<
      EnrollmentPayload,
      "challengeId" | "secret" | "deviceId" | "publicKeyJwk" | "signature"
    >
  >,
): Promise<boolean> {
  try {
    const key = await crypto.subtle.importKey(
      "jwk",
      payload.publicKeyJwk,
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["verify"],
    );
    const message = new TextEncoder().encode(
      `munshi-enroll\n${payload.challengeId}\n${payload.secret}\n${payload.deviceId}`,
    );
    return crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      key,
      decodeBase64Url(payload.signature),
      message,
    );
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  try {
    const payload = (await request.json()) as EnrollmentPayload;
    const challengeId = payload.challengeId?.trim() ?? "";
    const secret = payload.secret?.trim() ?? "";
    const deviceId = payload.deviceId?.trim() ?? "";
    const labelCiphertext = payload.labelCiphertext?.trim() ?? "";
    const platform = normalizePlatform(payload.platform);
    const signature = payload.signature?.trim() ?? "";

    if (
      !challengeId ||
      secret.length < 32 ||
      !deviceId ||
      !labelCiphertext ||
      labelCiphertext.length > 4_096 ||
      !platform ||
      !payload.publicKeyJwk ||
      !signature
    ) {
      return Response.json(
        { error: "Invalid enrollment request." },
        { status: 400 },
      );
    }

    const challenge = await getDb().query.pairingChallenges.findFirst({
      where: eq(pairingChallenges.id, challengeId),
    });
    const now = new Date().toISOString();
    if (
      !challenge ||
      challenge.usedAt ||
      challenge.expiresAt <= now ||
      challenge.secretSha256 !== (await sha256Hex(secret))
    ) {
      return Response.json(
        { error: "Pairing challenge is invalid or expired." },
        { status: 410 },
      );
    }

    const proofValid = await verifyEnrollmentProof({
      challengeId,
      secret,
      deviceId,
      publicKeyJwk: payload.publicKeyJwk,
      signature,
    });
    if (!proofValid) {
      return Response.json(
        { error: "Device-key proof failed." },
        { status: 401 },
      );
    }

    const credential = randomSecret();
    const credentialSha256 = await sha256Hex(credential);
    const publicKeyJwk = JSON.stringify(payload.publicKeyJwk);
    if (publicKeyJwk.length > 8_192) {
      return Response.json(
        { error: "Public key is too large." },
        { status: 400 },
      );
    }

    const insertDevice = env.DB.prepare(
      `INSERT INTO devices (
        id, workspace_id, pairing_challenge_id, label_ciphertext, platform,
        public_key_jwk, credential_sha256, status
      )
      SELECT ?, workspace_id, ?, ?, ?, ?, ?, 'ACTIVE'
      FROM pairing_challenges
      WHERE id = ? AND used_at IS NULL AND expires_at > ? AND secret_sha256 = ?`,
    ).bind(
      deviceId,
      challengeId,
      labelCiphertext,
      platform,
      publicKeyJwk,
      credentialSha256,
      challengeId,
      now,
      challenge.secretSha256,
    );
    const markUsed = env.DB.prepare(
      "UPDATE pairing_challenges SET used_at = ? WHERE id = ? AND used_at IS NULL",
    ).bind(now, challengeId);
    const [insertResult] = await env.DB.batch([insertDevice, markUsed]);
    if ((insertResult.meta.changes ?? 0) !== 1) {
      return Response.json(
        { error: "Pairing challenge was already used." },
        { status: 409 },
      );
    }

    return Response.json(
      {
        device: { id: deviceId, platform, status: "ACTIVE" },
        credential,
      },
      { status: 201 },
    );
  } catch (error) {
    return apiError(error);
  }
}
