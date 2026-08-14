import type { MasterProfile, ProfileFact } from "@munshi-apply/contracts";
import {
  encryptJson,
  getCloudSnapshot,
  getWorkspaceEncryptionKey,
  sha256Hex,
  type CloudConnection,
} from "./cloud";

export class ProtectedProfileConflictError extends Error {
  readonly keys: string[];

  constructor(keys: string[]) {
    super(
      `Protected profile facts changed on another device: ${keys.join(", ")}. Review the workspace before continuing.`,
    );
    this.name = "ProtectedProfileConflictError";
    this.keys = keys;
  }
}

function factValueFingerprint(value: ProfileFact["value"]): string {
  return JSON.stringify(value);
}

function isConfirmedProtectedFact(fact: ProfileFact): boolean {
  return fact.protected && fact.trustLevel !== "UNKNOWN";
}

export function protectedProfileConflictKeys(
  localProfile: MasterProfile,
  remoteProfile: MasterProfile,
): string[] {
  const remoteByKey = new Map(
    remoteProfile.facts.map((fact) => [fact.key, fact] as const),
  );
  return localProfile.facts
    .filter(isConfirmedProtectedFact)
    .filter((localFact) => {
      const remoteFact = remoteByKey.get(localFact.key);
      return (
        remoteFact !== undefined &&
        isConfirmedProtectedFact(remoteFact) &&
        factValueFingerprint(localFact.value) !==
          factValueFingerprint(remoteFact.value)
      );
    })
    .map((fact) => fact.key)
    .sort();
}

function assertNoProtectedConflict(
  localProfile: MasterProfile,
  remoteProfile: MasterProfile | null,
): void {
  if (!remoteProfile) return;
  const conflicts = protectedProfileConflictKeys(localProfile, remoteProfile);
  if (conflicts.length > 0) {
    throw new ProtectedProfileConflictError(conflicts);
  }
}

async function postProfile(
  connection: CloudConnection,
  rawKey: string,
  profile: MasterProfile,
  baseVersion: number,
): Promise<void> {
  const payloadCiphertext = await encryptJson(rawKey, profile);
  const response = await fetch(`${connection.baseUrl}/api/sync/events`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${connection.credential}`,
    },
    body: JSON.stringify({
      id: `evt-${crypto.randomUUID()}`,
      correlationId: `cor-${crypto.randomUUID()}`,
      entityType: "PROFILE.V1",
      entityId: "profile-master",
      baseVersion,
      schemaVersion: "1.0",
      payloadCiphertext,
      payloadSha256: await sha256Hex(payloadCiphertext),
    }),
  });
  const payload = (await response.json()) as {
    conflict?: { expectedVersion?: number };
    error?: string;
  };
  if (response.status === 409) {
    throw new Error(
      `Profile changed on another device (version ${payload.conflict?.expectedVersion ?? "unknown"}). Refresh and review before saving again.`,
    );
  }
  if (!response.ok) {
    throw new Error(payload.error ?? "Encrypted profile update failed");
  }
}

export async function synchronizeProtectedProfile(
  connection: CloudConnection,
  localProfile: MasterProfile,
): Promise<MasterProfile> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");

  // Read exactly one authoritative remote version. The POST below uses that
  // version as its optimistic-concurrency base so an intervening device write
  // is rejected by the server rather than silently overwritten.
  const snapshot = await getCloudSnapshot(connection);
  assertNoProtectedConflict(localProfile, snapshot.profile);

  if (!snapshot.profile) {
    if (localProfile.facts.length > 0) {
      await postProfile(connection, rawKey, localProfile, 0);
    }
    return localProfile;
  }

  if (localProfile.updatedAt > snapshot.profile.updatedAt) {
    await postProfile(
      connection,
      rawKey,
      localProfile,
      snapshot.profileVersion,
    );
    return localProfile;
  }

  return snapshot.profile;
}
