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

function isConfirmedProtectedFact(fact: ProfileFact | undefined): boolean {
  return Boolean(fact?.protected && fact.trustLevel !== "UNKNOWN");
}

function laterFact(
  left: ProfileFact | undefined,
  right: ProfileFact | undefined,
): ProfileFact | undefined {
  if (!left) return right;
  if (!right) return left;
  return left.updatedAt >= right.updatedAt ? left : right;
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
        isConfirmedProtectedFact(remoteFact) &&
        factValueFingerprint(localFact.value) !==
          factValueFingerprint(remoteFact!.value)
      );
    })
    .map((fact) => fact.key)
    .sort();
}

export function reconcileProtectedProfile(
  localProfile: MasterProfile,
  remoteProfile: MasterProfile,
): MasterProfile {
  const conflicts = protectedProfileConflictKeys(localProfile, remoteProfile);
  if (conflicts.length > 0) {
    throw new ProtectedProfileConflictError(conflicts);
  }

  const base =
    localProfile.updatedAt > remoteProfile.updatedAt
      ? localProfile
      : remoteProfile;
  const localByKey = new Map(
    localProfile.facts.map((fact) => [fact.key, fact] as const),
  );
  const remoteByKey = new Map(
    remoteProfile.facts.map((fact) => [fact.key, fact] as const),
  );
  const protectedKeys = new Set(
    [...localProfile.facts, ...remoteProfile.facts]
      .filter((fact) => fact.protected)
      .map((fact) => fact.key),
  );
  const selectedProtected = new Map<string, ProfileFact>();

  for (const key of protectedKeys) {
    const localFact = localByKey.get(key);
    const remoteFact = remoteByKey.get(key);
    const selected = isConfirmedProtectedFact(localFact)
      ? localFact
      : isConfirmedProtectedFact(remoteFact)
        ? remoteFact
        : laterFact(localFact, remoteFact);
    if (selected) selectedProtected.set(key, selected);
  }

  const facts = base.facts
    .filter((fact) => !protectedKeys.has(fact.key))
    .concat([...selectedProtected.values()])
    .sort((left, right) => left.key.localeCompare(right.key));

  return {
    ...base,
    profileId: remoteProfile.profileId,
    createdAt:
      localProfile.createdAt < remoteProfile.createdAt
        ? localProfile.createdAt
        : remoteProfile.createdAt,
    facts,
  };
}

function sameProfile(left: MasterProfile, right: MasterProfile): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
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

  // Read exactly one authoritative remote version. Any later write races the
  // POST below and is rejected by optimistic concurrency instead of silently
  // overwriting a protected decision.
  const snapshot = await getCloudSnapshot(connection);
  if (!snapshot.profile) {
    if (localProfile.facts.length > 0) {
      await postProfile(connection, rawKey, localProfile, 0);
    }
    return localProfile;
  }

  const reconciled = reconcileProtectedProfile(localProfile, snapshot.profile);
  if (sameProfile(reconciled, snapshot.profile)) return snapshot.profile;

  const synchronized = {
    ...reconciled,
    updatedAt: new Date().toISOString(),
  };
  await postProfile(
    connection,
    rawKey,
    synchronized,
    snapshot.profileVersion,
  );
  return synchronized;
}
