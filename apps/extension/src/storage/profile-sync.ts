import type { MasterProfile, ProfileFact } from "@munshi-apply/contracts";
import {
  parseProfileSnapshot,
  type ProfileRecord,
  type ProfileRecordTombstone,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";
import {
  getCloudSnapshot,
  getWorkspaceEncryptionKey,
  postEncryptedEntity,
  type CloudConnection,
} from "./cloud";

export type ProtectedProfileConflictWinner = "local" | "remote";

export type ProtectedProfileConflictDetail = {
  key: string;
  localValue: ProfileFact["value"] | null;
  remoteValue: ProfileFact["value"] | null;
};

export class ProtectedProfileConflictError extends Error {
  readonly keys: string[];
  readonly details: ProtectedProfileConflictDetail[];

  constructor(keys: string[], details: ProtectedProfileConflictDetail[] = []) {
    super(
      `Protected profile facts changed on another device: ${keys.join(", ")}. Review the workspace before continuing.`,
    );
    this.name = "ProtectedProfileConflictError";
    this.keys = keys;
    this.details = details;
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

function conflictValue(
  profile: ProfileSnapshot,
  key: string,
): ProfileFact["value"] | null {
  if (!key.startsWith("record:")) {
    return profile.facts.find((fact) => fact.key === key)?.value ?? null;
  }
  const [, recordId, factKey] = key.split(":");
  const record = profile.records.find(
    (candidate) => candidate.recordId === recordId,
  );
  if (!record) return null;
  if (factKey === "kind") return record.kind;
  return record.facts.find((fact) => fact.key === factKey)?.value ?? null;
}

export function protectedProfileConflictDetails(
  localProfile: ProfileSnapshot,
  remoteProfile: ProfileSnapshot,
): ProtectedProfileConflictDetail[] {
  return protectedProfileConflictKeys(localProfile, remoteProfile).map(
    (key) => ({
      key,
      localValue: conflictValue(localProfile, key),
      remoteValue: conflictValue(remoteProfile, key),
    }),
  );
}

function chooseProtectedFact(
  baseFact: ProfileFact | undefined,
  localFact: ProfileFact | undefined,
  remoteFact: ProfileFact | undefined,
  winner: ProtectedProfileConflictWinner | null,
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
    if (winner === "local") return localFact;
    if (winner === "remote") return remoteFact;
  }
  if (isConfirmedProtectedFact(localFact)) return localFact;
  if (isConfirmedProtectedFact(remoteFact)) return remoteFact;
  return baseFact ?? laterFact(localFact, remoteFact);
}

function reconcileFacts(
  baseFacts: ProfileFact[],
  localFacts: ProfileFact[],
  remoteFacts: ProfileFact[],
  protectedWinner: ProtectedProfileConflictWinner | null = null,
): ProfileFact[] {
  const baseByKey = new Map(baseFacts.map((fact) => [fact.key, fact] as const));
  const localByKey = new Map(
    localFacts.map((fact) => [fact.key, fact] as const),
  );
  const remoteByKey = new Map(
    remoteFacts.map((fact) => [fact.key, fact] as const),
  );
  const allKeys = new Set(
    [...baseFacts, ...localFacts, ...remoteFacts].map((fact) => fact.key),
  );
  const selected = new Map<string, ProfileFact>();

  for (const key of allKeys) {
    const baseFact = baseByKey.get(key);
    const localFact = localByKey.get(key);
    const remoteFact = remoteByKey.get(key);
    const protectedFact = Boolean(
      baseFact?.protected || localFact?.protected || remoteFact?.protected,
    );
    const ordinaryChoice = !localFact
      ? (remoteFact ?? baseFact)
      : !remoteFact
        ? localFact
        : localFact.updatedAt > remoteFact.updatedAt
          ? localFact
          : remoteFact.updatedAt > localFact.updatedAt
            ? remoteFact
            : (baseFact ?? localFact);
    const choice = protectedFact
      ? chooseProtectedFact(baseFact, localFact, remoteFact, protectedWinner)
      : ordinaryChoice;
    if (choice) selected.set(key, choice);
  }

  const facts = baseFacts.map((fact) => selected.get(fact.key) ?? fact);
  const seen = new Set(facts.map((fact) => fact.key));
  for (const key of [...selected.keys()].sort()) {
    if (!seen.has(key)) facts.push(selected.get(key)!);
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
  protectedWinner: ProtectedProfileConflictWinner | null,
): ProfileRecord {
  if (local.kind !== remote.kind) {
    if (protectedWinner === "local") return local;
    if (protectedWinner === "remote") return remote;
    throw new ProtectedProfileConflictError([`record:${local.recordId}:kind`]);
  }
  const conflicts = protectedFactConflictKeys(
    local.facts,
    remote.facts,
    `record:${local.recordId}:`,
  );
  if (conflicts.length > 0 && !protectedWinner) {
    throw new ProtectedProfileConflictError(conflicts);
  }
  const base = local.updatedAt > remote.updatedAt ? local : remote;
  return {
    ...base,
    createdAt:
      local.createdAt < remote.createdAt ? local.createdAt : remote.createdAt,
    facts: reconcileFacts(
      base.facts,
      local.facts,
      remote.facts,
      protectedWinner,
    ),
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
  protectedWinner: ProtectedProfileConflictWinner | null,
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
      const record = reconcileRecord(
        localEvent.record,
        remoteEvent.record,
        protectedWinner,
      );
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
  protectedWinner: ProtectedProfileConflictWinner | null = null,
): ProfileSnapshot {
  const conflicts = protectedProfileConflictKeys(localProfile, remoteProfile);
  if (conflicts.length > 0 && !protectedWinner) {
    throw new ProtectedProfileConflictError(
      conflicts,
      protectedProfileConflictDetails(localProfile, remoteProfile),
    );
  }

  const base =
    localProfile.updatedAt > remoteProfile.updatedAt
      ? localProfile
      : remoteProfile;
  const recordState = reconcileRecordEvents(
    localProfile,
    remoteProfile,
    protectedWinner,
  );

  return parseProfileSnapshot({
    ...masterProfile(base),
    profileId: remoteProfile.profileId,
    createdAt:
      localProfile.createdAt < remoteProfile.createdAt
        ? localProfile.createdAt
        : remoteProfile.createdAt,
    facts: reconcileFacts(
      base.facts,
      localProfile.facts,
      remoteProfile.facts,
      protectedWinner,
    ),
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
  return postEncryptedEntity({
    connection,
    rawKey,
    entityType: "PROFILE.V1",
    entityId: "profile-master",
    baseVersion,
    value: profile,
  });
}

export async function resolveProtectedProfileConflict(
  connection: CloudConnection,
  localProfile: ProfileSnapshot,
  winner: ProtectedProfileConflictWinner,
): Promise<ProfileSnapshot> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");

  const snapshot = await getCloudSnapshot(connection);
  if (!snapshot.profile) {
    throw new Error("No encrypted workspace profile exists to resolve");
  }
  const conflicts = protectedProfileConflictKeys(
    localProfile,
    snapshot.profile,
  );
  if (conflicts.length === 0) {
    return synchronizeProtectedProfile(connection, localProfile);
  }
  const resolved = reconcileProtectedProfile(
    localProfile,
    snapshot.profile,
    winner,
  );
  const synchronized = parseProfileSnapshot({
    ...resolved,
    updatedAt: new Date().toISOString(),
  });
  await postProfile(connection, rawKey, synchronized, snapshot.profileVersion);
  return synchronized;
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
