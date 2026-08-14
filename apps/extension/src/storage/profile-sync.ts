import type { MasterProfile, ProfileFact } from "@munshi-apply/contracts";
import {
  parseProfileSnapshot,
  type ProfileRecord,
  type ProfileRecordTombstone,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";
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

function protectedFactConflictKeys(
  localFacts: ProfileFact[],
  remoteFacts: ProfileFact[],
  prefix = "",
): string[] {
  const remoteByKey = new Map(
    remoteFacts.map((fact) => [fact.key, fact] as const),
  );
  return localFacts
    .filter(isConfirmedProtectedFact)
    .filter((localFact) => {
      const remoteFact = remoteByKey.get(localFact.key);
      return (
        isConfirmedProtectedFact(remoteFact) &&
        factValueFingerprint(localFact.value) !==
          factValueFingerprint(remoteFact!.value)
      );
    })
    .map((fact) => `${prefix}${fact.key}`)
    .sort();
}

export function protectedProfileConflictKeys(
  localProfile: ProfileSnapshot,
  remoteProfile: ProfileSnapshot,
): string[] {
  const conflicts = protectedFactConflictKeys(
    localProfile.facts,
    remoteProfile.facts,
  );
  const remoteRecords = new Map(
    remoteProfile.records.map((record) => [record.recordId, record] as const),
  );
  for (const localRecord of localProfile.records) {
    const remoteRecord = remoteRecords.get(localRecord.recordId);
    if (!remoteRecord) continue;
    if (localRecord.kind !== remoteRecord.kind) {
      conflicts.push(`record:${localRecord.recordId}:kind`);
      continue;
    }
    conflicts.push(
      ...protectedFactConflictKeys(
        localRecord.facts,
        remoteRecord.facts,
        `record:${localRecord.recordId}:`,
      ),
    );
  }
  return [...new Set(conflicts)].sort();
}

function chooseProtectedFact(
  baseFact: ProfileFact | undefined,
  localFact: ProfileFact | undefined,
  remoteFact: ProfileFact | undefined,
): ProfileFact | undefined {
  if (localFact && remoteFact) {
    const sameValue =
      factValueFingerprint(localFact.value) ===
      factValueFingerprint(remoteFact.value);
    if (sameValue) {
      if (isConfirmedProtectedFact(baseFact)) return baseFact;
      if (isConfirmedProtectedFact(localFact)) return localFact;
      if (isConfirmedProtectedFact(remoteFact)) return remoteFact;
      return baseFact ?? laterFact(localFact, remoteFact);
    }
  }
  if (isConfirmedProtectedFact(localFact)) return localFact;
  if (isConfirmedProtectedFact(remoteFact)) return remoteFact;
  return baseFact ?? laterFact(localFact, remoteFact);
}

function reconcileFacts(
  baseFacts: ProfileFact[],
  localFacts: ProfileFact[],
  remoteFacts: ProfileFact[],
): ProfileFact[] {
  const baseByKey = new Map(baseFacts.map((fact) => [fact.key, fact] as const));
  const localByKey = new Map(
    localFacts.map((fact) => [fact.key, fact] as const),
  );
  const remoteByKey = new Map(
    remoteFacts.map((fact) => [fact.key, fact] as const),
  );
  const protectedKeys = new Set(
    [...localFacts, ...remoteFacts]
      .filter((fact) => fact.protected)
      .map((fact) => fact.key),
  );
  const selectedProtected = new Map<string, ProfileFact>();

  for (const key of protectedKeys) {
    const selected = chooseProtectedFact(
      baseByKey.get(key),
      localByKey.get(key),
      remoteByKey.get(key),
    );
    if (selected) selectedProtected.set(key, selected);
  }

  const facts = baseFacts.map(
    (fact) => selectedProtected.get(fact.key) ?? fact,
  );
  const seen = new Set(facts.map((fact) => fact.key));
  for (const key of [...selectedProtected.keys()].sort()) {
    if (!seen.has(key)) facts.push(selectedProtected.get(key)!);
  }
  return facts;
}

function masterProfile(snapshot: ProfileSnapshot): MasterProfile {
  return {
    profileId: snapshot.profileId,
    displayName: snapshot.displayName,
    facts: snapshot.facts,
    createdAt: snapshot.createdAt,
    updatedAt: snapshot.updatedAt,
    schemaVersion: snapshot.schemaVersion,
  };
}

function reconcileRecord(
  local: ProfileRecord,
  remote: ProfileRecord,
): ProfileRecord {
  if (local.kind !== remote.kind) {
    throw new ProtectedProfileConflictError([`record:${local.recordId}:kind`]);
  }
  const conflicts = protectedFactConflictKeys(
    local.facts,
    remote.facts,
    `record:${local.recordId}:`,
  );
  if (conflicts.length > 0) throw new ProtectedProfileConflictError(conflicts);
  const base = local.updatedAt > remote.updatedAt ? local : remote;
  return {
    ...base,
    createdAt:
      local.createdAt < remote.createdAt ? local.createdAt : remote.createdAt,
    facts: reconcileFacts(base.facts, local.facts, remote.facts),
  };
}

type RecordEvent =
  | { timestamp: string; record: ProfileRecord; tombstone?: never }
  | {
      timestamp: string;
      record?: never;
      tombstone: ProfileRecordTombstone;
    };

function recordEvents(snapshot: ProfileSnapshot): Map<string, RecordEvent> {
  const events = new Map<string, RecordEvent>();
  for (const record of snapshot.records) {
    events.set(record.recordId, { timestamp: record.updatedAt, record });
  }
  for (const tombstone of snapshot.recordTombstones) {
    events.set(tombstone.recordId, {
      timestamp: tombstone.deletedAt,
      tombstone,
    });
  }
  return events;
}

function reconcileRecordEvents(
  local: ProfileSnapshot,
  remote: ProfileSnapshot,
): {
  records: ProfileRecord[];
  recordTombstones: ProfileRecordTombstone[];
} {
  const localEvents = recordEvents(local);
  const remoteEvents = recordEvents(remote);
  const records: ProfileRecord[] = [];
  const recordTombstones: ProfileRecordTombstone[] = [];
  const recordIds = [
    ...new Set([...localEvents.keys(), ...remoteEvents.keys()]),
  ].sort();

  for (const recordId of recordIds) {
    const localEvent = localEvents.get(recordId);
    const remoteEvent = remoteEvents.get(recordId);
    let selected: RecordEvent | undefined;
    if (localEvent?.record && remoteEvent?.record) {
      const record = reconcileRecord(localEvent.record, remoteEvent.record);
      selected = { timestamp: record.updatedAt, record };
    } else if (!localEvent) {
      selected = remoteEvent;
    } else if (!remoteEvent) {
      selected = localEvent;
    } else {
      selected =
        localEvent.timestamp > remoteEvent.timestamp ? localEvent : remoteEvent;
    }
    if (selected?.record) records.push(selected.record);
    if (selected?.tombstone) recordTombstones.push(selected.tombstone);
  }

  records.sort(
    (left, right) =>
      left.kind.localeCompare(right.kind) ||
      left.sortOrder - right.sortOrder ||
      left.recordId.localeCompare(right.recordId),
  );
  recordTombstones.sort(
    (left, right) =>
      left.deletedAt.localeCompare(right.deletedAt) ||
      left.recordId.localeCompare(right.recordId),
  );
  return { records, recordTombstones };
}

export function reconcileProtectedProfile(
  localProfile: ProfileSnapshot,
  remoteProfile: ProfileSnapshot,
): ProfileSnapshot {
  const conflicts = protectedProfileConflictKeys(localProfile, remoteProfile);
  if (conflicts.length > 0) {
    throw new ProtectedProfileConflictError(conflicts);
  }

  const base =
    localProfile.updatedAt > remoteProfile.updatedAt
      ? localProfile
      : remoteProfile;
  const recordState = reconcileRecordEvents(localProfile, remoteProfile);

  return parseProfileSnapshot({
    ...masterProfile(base),
    profileId: remoteProfile.profileId,
    createdAt:
      localProfile.createdAt < remoteProfile.createdAt
        ? localProfile.createdAt
        : remoteProfile.createdAt,
    facts: reconcileFacts(base.facts, localProfile.facts, remoteProfile.facts),
    ...recordState,
    snapshotVersion: 1,
  });
}

function sameProfile(left: ProfileSnapshot, right: ProfileSnapshot): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

async function postProfile(
  connection: CloudConnection,
  rawKey: string,
  profile: ProfileSnapshot,
  baseVersion: number,
): Promise<number> {
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
    event?: { version?: number };
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
  const expectedVersion = baseVersion + 1;
  if (payload.event?.version !== expectedVersion) {
    throw new Error(
      "Encrypted profile update was not acknowledged at the expected version",
    );
  }
  return expectedVersion;
}

export async function synchronizeProtectedProfile(
  connection: CloudConnection,
  localProfile: ProfileSnapshot,
): Promise<ProfileSnapshot> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");

  // Read exactly one authoritative remote version. Any later write races the
  // POST below and is rejected by optimistic concurrency instead of silently
  // overwriting a protected decision.
  const snapshot = await getCloudSnapshot(connection);
  if (!snapshot.profile) {
    if (localProfile.facts.length > 0 || localProfile.records.length > 0) {
      await postProfile(connection, rawKey, localProfile, 0);
    }
    return localProfile;
  }

  const reconciled = reconcileProtectedProfile(localProfile, snapshot.profile);
  if (sameProfile(reconciled, snapshot.profile)) return snapshot.profile;

  const synchronized = parseProfileSnapshot({
    ...reconciled,
    updatedAt: new Date().toISOString(),
  });
  await postProfile(connection, rawKey, synchronized, snapshot.profileVersion);
  return synchronized;
}
