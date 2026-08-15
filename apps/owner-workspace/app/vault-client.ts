"use client";

export type ProfileFact = {
  factId: string;
  key: string;
  value: string | number | boolean | string[];
  category: string;
  trustLevel:
    | "VERIFIED"
    | "USER_CONFIRMED"
    | "DOCUMENT_CONFIRMED"
    | "DERIVED"
    | "GENERATED"
    | "LEARNED"
    | "UNKNOWN";
  source: string;
  confirmedAt: string | null;
  updatedAt: string;
  protected: boolean;
};

export type ProfileRecordKind =
  "EDUCATION" | "EMPLOYMENT" | "PROJECT" | "CERTIFICATION" | "LANGUAGE";

export type ProfileRecord = {
  recordId: string;
  kind: ProfileRecordKind;
  label: string;
  facts: ProfileFact[];
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
};

export type ProfileRecordTombstone = {
  recordId: string;
  kind: ProfileRecordKind;
  deletedAt: string;
  confirmed: true;
};

export type ProfileSnapshot = {
  profileId: string;
  displayName: string;
  facts: ProfileFact[];
  records: ProfileRecord[];
  recordTombstones: ProfileRecordTombstone[];
  createdAt: string;
  updatedAt: string;
  schemaVersion: 1;
  snapshotVersion: 1;
};

export type MasterProfile = ProfileSnapshot;

const trustLevels = new Set<ProfileFact["trustLevel"]>([
  "VERIFIED",
  "USER_CONFIRMED",
  "DOCUMENT_CONFIRMED",
  "DERIVED",
  "GENERATED",
  "LEARNED",
  "UNKNOWN",
]);
const profileRecordKinds = new Set<ProfileRecordKind>([
  "EDUCATION",
  "EMPLOYMENT",
  "PROJECT",
  "CERTIFICATION",
  "LANGUAGE",
]);

function recordValue(value: unknown, error: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(error);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, error: string): string {
  if (typeof value !== "string" || !value) throw new Error(error);
  return value;
}

function timestamp(value: unknown, error: string): string {
  const candidate = requiredString(value, error);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(candidate)) {
    throw new Error(error);
  }
  return candidate;
}

function parseProfileFact(value: unknown): ProfileFact {
  const candidate = recordValue(value, "Encrypted profile fact is invalid.");
  const factValue = candidate.value;
  if (
    typeof factValue !== "string" &&
    typeof factValue !== "number" &&
    typeof factValue !== "boolean" &&
    !(
      Array.isArray(factValue) &&
      factValue.every((item) => typeof item === "string")
    )
  ) {
    throw new Error("Encrypted profile fact value is invalid.");
  }
  if (
    typeof candidate.trustLevel !== "string" ||
    !trustLevels.has(candidate.trustLevel as ProfileFact["trustLevel"])
  ) {
    throw new Error("Encrypted profile fact trust level is invalid.");
  }
  if (candidate.confirmedAt !== null && candidate.confirmedAt !== undefined) {
    timestamp(
      candidate.confirmedAt,
      "Encrypted profile confirmation is invalid.",
    );
  }
  if (typeof candidate.protected !== "boolean") {
    throw new Error("Encrypted profile protection marker is invalid.");
  }
  return {
    factId: requiredString(
      candidate.factId,
      "Encrypted profile fact id is invalid.",
    ),
    key: requiredString(
      candidate.key,
      "Encrypted profile fact key is invalid.",
    ),
    value: factValue,
    category: requiredString(
      candidate.category,
      "Encrypted profile fact category is invalid.",
    ),
    trustLevel: candidate.trustLevel as ProfileFact["trustLevel"],
    source: requiredString(
      candidate.source,
      "Encrypted profile fact source is invalid.",
    ),
    confirmedAt:
      candidate.confirmedAt == null
        ? null
        : timestamp(
            candidate.confirmedAt,
            "Encrypted profile confirmation is invalid.",
          ),
    updatedAt: timestamp(
      candidate.updatedAt,
      "Encrypted profile update time is invalid.",
    ),
    protected: candidate.protected,
  };
}

function parseRecordKind(value: unknown): ProfileRecordKind {
  if (
    typeof value !== "string" ||
    !profileRecordKinds.has(value as ProfileRecordKind)
  ) {
    throw new Error("Encrypted profile record kind is invalid.");
  }
  return value as ProfileRecordKind;
}

export function parseProfileSnapshot(value: unknown): ProfileSnapshot {
  const candidate = recordValue(
    value,
    "Encrypted profile snapshot is invalid.",
  );
  if (!Array.isArray(candidate.facts)) {
    throw new Error("Encrypted profile facts are invalid.");
  }
  if (candidate.records !== undefined && !Array.isArray(candidate.records)) {
    throw new Error("Encrypted profile records are invalid.");
  }
  if (
    candidate.recordTombstones !== undefined &&
    !Array.isArray(candidate.recordTombstones)
  ) {
    throw new Error("Encrypted profile deletion history is invalid.");
  }
  if (candidate.schemaVersion !== 1) {
    throw new Error("Encrypted profile schema version is unsupported.");
  }
  if (
    candidate.snapshotVersion !== undefined &&
    candidate.snapshotVersion !== 1
  ) {
    throw new Error("Encrypted profile snapshot version is unsupported.");
  }

  const facts = candidate.facts.map(parseProfileFact);
  const records = (candidate.records ?? []).map((value) => {
    const record = recordValue(value, "Encrypted profile record is invalid.");
    if (!Array.isArray(record.facts)) {
      throw new Error("Encrypted profile record facts are invalid.");
    }
    const sortOrder = record.sortOrder ?? 0;
    if (!Number.isInteger(sortOrder) || (sortOrder as number) < 0) {
      throw new Error("Encrypted profile record order is invalid.");
    }
    return {
      recordId: requiredString(
        record.recordId,
        "Encrypted profile record id is invalid.",
      ),
      kind: parseRecordKind(record.kind),
      label: requiredString(
        record.label,
        "Encrypted profile record label is invalid.",
      ),
      facts: record.facts.map(parseProfileFact),
      sortOrder: sortOrder as number,
      createdAt: timestamp(
        record.createdAt,
        "Encrypted profile record creation time is invalid.",
      ),
      updatedAt: timestamp(
        record.updatedAt,
        "Encrypted profile record update time is invalid.",
      ),
    } satisfies ProfileRecord;
  });
  const recordTombstones = (candidate.recordTombstones ?? []).map((value) => {
    const tombstone = recordValue(
      value,
      "Encrypted profile deletion marker is invalid.",
    );
    if (tombstone.confirmed !== true) {
      throw new Error("Encrypted profile deletion was not confirmed.");
    }
    return {
      recordId: requiredString(
        tombstone.recordId,
        "Encrypted profile deletion id is invalid.",
      ),
      kind: parseRecordKind(tombstone.kind),
      deletedAt: timestamp(
        tombstone.deletedAt,
        "Encrypted profile deletion time is invalid.",
      ),
      confirmed: true,
    } satisfies ProfileRecordTombstone;
  });

  const factIds = new Set<string>();
  for (const fact of facts) {
    if (factIds.has(fact.factId)) {
      throw new Error(`Duplicate encrypted profile fact id: ${fact.factId}`);
    }
    factIds.add(fact.factId);
  }
  const recordIds = new Set<string>();
  for (const record of records) {
    if (recordIds.has(record.recordId)) {
      throw new Error(
        `Duplicate encrypted profile record id: ${record.recordId}`,
      );
    }
    recordIds.add(record.recordId);
    const keys = new Set<string>();
    for (const fact of record.facts) {
      if (keys.has(fact.key)) {
        throw new Error(
          `Duplicate fact key in ${record.recordId}: ${fact.key}`,
        );
      }
      keys.add(fact.key);
      if (factIds.has(fact.factId)) {
        throw new Error(`Duplicate encrypted profile fact id: ${fact.factId}`);
      }
      factIds.add(fact.factId);
    }
  }
  const tombstoneIds = new Set<string>();
  for (const tombstone of recordTombstones) {
    if (tombstoneIds.has(tombstone.recordId)) {
      throw new Error(`Duplicate profile deletion id: ${tombstone.recordId}`);
    }
    if (recordIds.has(tombstone.recordId)) {
      throw new Error(
        `Profile record and deletion overlap: ${tombstone.recordId}`,
      );
    }
    tombstoneIds.add(tombstone.recordId);
  }

  return {
    profileId: requiredString(
      candidate.profileId,
      "Encrypted profile id is invalid.",
    ),
    displayName: requiredString(
      candidate.displayName,
      "Encrypted profile name is invalid.",
    ),
    facts,
    records,
    recordTombstones,
    createdAt: timestamp(
      candidate.createdAt,
      "Encrypted profile creation time is invalid.",
    ),
    updatedAt: timestamp(
      candidate.updatedAt,
      "Encrypted profile update time is invalid.",
    ),
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

const legacyRecordMappings: ReadonlyArray<{
  kind: ProfileRecordKind;
  primaryKey: string;
  fallbackLabel: string;
  keys: Record<string, string>;
}> = [
  {
    kind: "EDUCATION",
    primaryKey: "school_name",
    fallbackLabel: "Imported education",
    keys: {
      school_name: "school_name",
      highest_degree: "degree",
      field_of_study: "field_of_study",
      graduation_date: "graduation_date",
      gpa: "gpa",
    },
  },
  {
    kind: "EMPLOYMENT",
    primaryKey: "employer_name",
    fallbackLabel: "Imported employment",
    keys: {
      current_employer: "employer_name",
      current_title: "job_title",
      employment_summary: "responsibilities",
    },
  },
  {
    kind: "PROJECT",
    primaryKey: "project_summary",
    fallbackLabel: "Imported project",
    keys: { project_summary: "project_summary" },
  },
  {
    kind: "CERTIFICATION",
    primaryKey: "certification_name",
    fallbackLabel: "Imported certification",
    keys: { certifications: "certification_name" },
  },
  {
    kind: "LANGUAGE",
    primaryKey: "language",
    fallbackLabel: "Imported language",
    keys: { languages: "language" },
  },
];

function hasFactValue(fact: ProfileFact): boolean {
  return Array.isArray(fact.value)
    ? fact.value.length > 0
    : String(fact.value).trim().length > 0;
}

export function migrateLegacyProfileSnapshot(value: unknown): {
  snapshot: ProfileSnapshot;
  migrated: boolean;
} {
  const snapshot = parseProfileSnapshot(value);
  const records = [...snapshot.records];
  let migrated = false;
  for (const mapping of legacyRecordMappings) {
    if (records.some((record) => record.kind === mapping.kind)) continue;
    const recordFacts = Object.entries(mapping.keys)
      .map(([legacyKey, recordKey]) => {
        const fact = snapshot.facts.find(
          (candidate) => candidate.key === legacyKey && hasFactValue(candidate),
        );
        return fact
          ? {
              ...fact,
              factId: `${fact.factId}:record:${mapping.kind.toLowerCase()}`,
              key: recordKey,
              source: `${fact.source}:LEGACY_MIGRATION`,
            }
          : null;
      })
      .filter((fact): fact is ProfileFact => fact !== null);
    if (recordFacts.length === 0) continue;
    const primary = recordFacts.find((fact) => fact.key === mapping.primaryKey);
    const updatedAt = recordFacts
      .map((fact) => fact.updatedAt)
      .sort((left, right) => right.localeCompare(left))[0]!;
    records.push({
      recordId: `legacy-${mapping.kind.toLowerCase()}-${snapshot.profileId}`,
      kind: mapping.kind,
      label:
        primary && typeof primary.value === "string" && primary.value.trim()
          ? primary.value.trim()
          : mapping.fallbackLabel,
      facts: recordFacts,
      sortOrder: 0,
      createdAt: snapshot.createdAt,
      updatedAt,
    });
    migrated = true;
  }
  return migrated
    ? { snapshot: parseProfileSnapshot({ ...snapshot, records }), migrated }
    : { snapshot, migrated };
}

export class ProtectedProfileConflictError extends Error {
  readonly keys: string[];

  constructor(keys: string[]) {
    super(
      `Protected profile facts changed on another device: ${keys.join(", ")}. Review them before synchronizing.`,
    );
    this.name = "ProtectedProfileConflictError";
    this.keys = keys;
  }
}

function factFingerprint(value: ProfileFact["value"]): string {
  return JSON.stringify(value);
}

function confirmedProtected(fact: ProfileFact | undefined): boolean {
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

function protectedFactConflicts(
  localFacts: ProfileFact[],
  remoteFacts: ProfileFact[],
  prefix = "",
): string[] {
  const remoteByKey = new Map(remoteFacts.map((fact) => [fact.key, fact]));
  return localFacts
    .filter(confirmedProtected)
    .filter((localFact) => {
      const remoteFact = remoteByKey.get(localFact.key);
      return (
        confirmedProtected(remoteFact) &&
        factFingerprint(localFact.value) !== factFingerprint(remoteFact!.value)
      );
    })
    .map((fact) => `${prefix}${fact.key}`);
}

function reconcileFacts(
  baseFacts: ProfileFact[],
  localFacts: ProfileFact[],
  remoteFacts: ProfileFact[],
): ProfileFact[] {
  const baseByKey = new Map(baseFacts.map((fact) => [fact.key, fact]));
  const localByKey = new Map(localFacts.map((fact) => [fact.key, fact]));
  const remoteByKey = new Map(remoteFacts.map((fact) => [fact.key, fact]));
  const keys = new Set(
    [...baseFacts, ...localFacts, ...remoteFacts].map((fact) => fact.key),
  );
  const selected = new Map<string, ProfileFact>();
  for (const key of keys) {
    const baseFact = baseByKey.get(key);
    const localFact = localByKey.get(key);
    const remoteFact = remoteByKey.get(key);
    const protectedFact = Boolean(
      baseFact?.protected || localFact?.protected || remoteFact?.protected,
    );
    if (!protectedFact) {
      const choice =
        !localFact
          ? (remoteFact ?? baseFact)
          : !remoteFact
            ? localFact
            : localFact.updatedAt > remoteFact.updatedAt
              ? localFact
              : remoteFact.updatedAt > localFact.updatedAt
                ? remoteFact
                : (baseFact ?? localFact);
      if (choice) selected.set(key, choice);
      continue;
    }
    if (
      localFact &&
      remoteFact &&
      factFingerprint(localFact.value) === factFingerprint(remoteFact.value)
    ) {
      selected.set(
        key,
        (confirmedProtected(baseFact)
          ? baseFact
          : confirmedProtected(localFact)
            ? localFact
            : confirmedProtected(remoteFact)
              ? remoteFact
              : (baseFact ?? laterFact(localFact, remoteFact)))!,
      );
    } else {
      const choice = confirmedProtected(localFact)
        ? localFact
        : confirmedProtected(remoteFact)
          ? remoteFact
          : (baseFact ?? laterFact(localFact, remoteFact));
      if (choice) selected.set(key, choice);
    }
  }
  const result = baseFacts.map((fact) => selected.get(fact.key) ?? fact);
  const seen = new Set(result.map((fact) => fact.key));
  for (const key of [...selected.keys()].sort()) {
    if (!seen.has(key)) result.push(selected.get(key)!);
  }
  return result;
}

function recordEvents(snapshot: ProfileSnapshot): Map<
  string,
  | { timestamp: string; record: ProfileRecord; tombstone?: never }
  | {
      timestamp: string;
      record?: never;
      tombstone: ProfileRecordTombstone;
    }
> {
  const events = new Map<
    string,
    | { timestamp: string; record: ProfileRecord; tombstone?: never }
    | {
        timestamp: string;
        record?: never;
        tombstone: ProfileRecordTombstone;
      }
  >();
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

function reconcileRecord(
  local: ProfileRecord,
  remote: ProfileRecord,
  protectedWinner: "local" | "remote" | null,
): ProfileRecord {
  if (local.kind !== remote.kind) {
    throw new ProtectedProfileConflictError([`record:${local.recordId}:kind`]);
  }
  const conflicts = protectedFactConflicts(
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
    facts:
      protectedWinner === "remote"
        ? reconcileFacts(base.facts, remote.facts, local.facts)
        : reconcileFacts(base.facts, local.facts, remote.facts),
  };
}

export function reconcileProfileSnapshots(
  local: ProfileSnapshot,
  remote: ProfileSnapshot,
  protectedWinner: "local" | "remote" | null = null,
): ProfileSnapshot {
  const conflicts = protectedFactConflicts(local.facts, remote.facts);
  const remoteRecords = new Map(
    remote.records.map((record) => [record.recordId, record]),
  );
  for (const localRecord of local.records) {
    const remoteRecord = remoteRecords.get(localRecord.recordId);
    if (remoteRecord) {
      conflicts.push(
        ...protectedFactConflicts(
          localRecord.facts,
          remoteRecord.facts,
          `record:${localRecord.recordId}:`,
        ),
      );
    }
  }
  if (conflicts.length > 0 && !protectedWinner) {
    throw new ProtectedProfileConflictError([...new Set(conflicts)].sort());
  }

  const localEvents = recordEvents(local);
  const remoteEvents = recordEvents(remote);
  const records: ProfileRecord[] = [];
  const recordTombstones: ProfileRecordTombstone[] = [];
  for (const recordId of [
    ...new Set([...localEvents.keys(), ...remoteEvents.keys()]),
  ].sort()) {
    const localEvent = localEvents.get(recordId);
    const remoteEvent = remoteEvents.get(recordId);
    const selected =
      localEvent?.record && remoteEvent?.record
        ? {
            timestamp:
              localEvent.timestamp > remoteEvent.timestamp
                ? localEvent.timestamp
                : remoteEvent.timestamp,
            record: reconcileRecord(
              localEvent.record,
              remoteEvent.record,
              protectedWinner,
            ),
          }
        : !localEvent
          ? remoteEvent
          : !remoteEvent
            ? localEvent
            : localEvent.timestamp > remoteEvent.timestamp
              ? localEvent
              : remoteEvent;
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
  const base = local.updatedAt > remote.updatedAt ? local : remote;
  return parseProfileSnapshot({
    ...base,
    profileId: remote.profileId,
    createdAt:
      local.createdAt < remote.createdAt ? local.createdAt : remote.createdAt,
    facts:
      protectedWinner === "remote"
        ? reconcileFacts(base.facts, remote.facts, local.facts)
        : reconcileFacts(base.facts, local.facts, remote.facts),
    records,
    recordTombstones,
    snapshotVersion: 1,
  });
}

export type ResumeRecord = {
  resumeId: string;
  objectId: string;
  name: string;
  contentType: string;
  sizeBytes: number;
  addedAt: string;
};

export type ApplicationSnapshot = {
  pageId: string;
  title: string;
  url: string;
  observedAt: string;
  questions: Array<{
    questionId: string;
    controlId: string;
    rawText: string;
    semanticType: string;
    sensitive: boolean;
    requiresReview: boolean;
  }>;
};

export type ApplicationReview = {
  reviewId: string;
  pageId: string;
  resumeId: string | null;
  approvedAt: string;
  answers: Array<{
    questionId: string;
    controlId: string;
    value: string;
    approved: boolean;
    sensitive: boolean;
  }>;
};

export type SyncEvent = {
  sequence: number;
  id: string;
  deviceId: string | null;
  correlationId: string;
  entityType: string;
  entityId: string;
  baseVersion: number;
  schemaVersion: string;
  payloadCiphertext: string;
  payloadSha256: string;
  createdAt: string;
};

export type DecryptedEntity<T = unknown> = {
  event: SyncEvent;
  value: T;
  version: number;
};

type CipherEnvelope = {
  v: 1;
  alg: "A256GCM";
  iv: string;
  ciphertext: string;
};

const databaseName = "munshi-apply-owner-vault";
const databaseVersion = 1;
const settingsStore = "settings";
const workspaceKeyName = "workspace-key-v1";

function openVault(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, databaseVersion);
    request.onerror = () =>
      reject(request.error ?? new Error("Private vault could not be opened."));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(settingsStore)) {
        database.createObjectStore(settingsStore);
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function readSetting(key: IDBValidKey): Promise<unknown> {
  const database = await openVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(settingsStore, "readonly");
    const request = transaction.objectStore(settingsStore).get(key);
    request.onerror = () =>
      reject(request.error ?? new Error("Private vault read failed."));
    request.onsuccess = () => resolve(request.result);
    transaction.oncomplete = () => database.close();
  });
}

async function writeSetting(key: IDBValidKey, value: unknown): Promise<void> {
  const database = await openVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(settingsStore, "readwrite");
    transaction.objectStore(settingsStore).put(value, key);
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Private vault write failed."));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}

function toBase64Url(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function fromBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = atob(padded);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function validateWorkspaceKey(value: unknown): string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(value)) {
    throw new Error("The recovery key is invalid.");
  }
  if (fromBase64Url(value).byteLength !== 32) {
    throw new Error("The recovery key is invalid.");
  }
  return value;
}

export async function ensureWorkspaceKey(): Promise<string> {
  const existing = await readSetting(workspaceKeyName);
  if (existing) return validateWorkspaceKey(existing);
  const created = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  await writeSetting(workspaceKeyName, created);
  return created;
}

export async function getWorkspaceKey(): Promise<string | null> {
  const value = await readSetting(workspaceKeyName);
  return value ? validateWorkspaceKey(value) : null;
}

export async function importWorkspaceKey(value: string): Promise<void> {
  await writeSetting(workspaceKeyName, validateWorkspaceKey(value.trim()));
}

async function importAesKey(rawKey: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    fromBase64Url(validateWorkspaceKey(rawKey)),
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function encryptBytes(
  rawKey: string,
  value: Uint8Array<ArrayBuffer>,
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    await importAesKey(rawKey),
    value,
  );
  const envelope: CipherEnvelope = {
    v: 1,
    alg: "A256GCM",
    iv: toBase64Url(iv),
    ciphertext: toBase64Url(ciphertext),
  };
  return JSON.stringify(envelope);
}

export async function decryptBytes(
  rawKey: string,
  value: string,
): Promise<Uint8Array<ArrayBuffer>> {
  const envelope = JSON.parse(value) as Partial<CipherEnvelope>;
  if (
    envelope.v !== 1 ||
    envelope.alg !== "A256GCM" ||
    typeof envelope.iv !== "string" ||
    typeof envelope.ciphertext !== "string"
  ) {
    throw new Error("Encrypted workspace data is invalid.");
  }
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: fromBase64Url(envelope.iv) },
    await importAesKey(rawKey),
    fromBase64Url(envelope.ciphertext),
  );
  return new Uint8Array(plaintext);
}

export async function encryptJson(rawKey: string, value: unknown) {
  return encryptBytes(rawKey, new TextEncoder().encode(JSON.stringify(value)));
}

export async function decryptJson<T>(rawKey: string, value: string) {
  return JSON.parse(
    new TextDecoder().decode(await decryptBytes(rawKey, value)),
  ) as T;
}

export async function sha256Hex(value: string | ArrayBuffer): Promise<string> {
  const bytes =
    typeof value === "string" ? new TextEncoder().encode(value) : value;
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export function encryptedHistoryNeedsRecovery(input: {
  hasLocalKey: boolean;
  eventCount: number;
  encryptedObjectCount: number;
}): boolean {
  return (
    !input.hasLocalKey &&
    (input.eventCount > 0 || input.encryptedObjectCount > 0)
  );
}

export async function workspaceKeyFingerprint(rawKey: string): Promise<string> {
  return (await sha256Hex(validateWorkspaceKey(rawKey))).slice(0, 16);
}

export async function fetchSyncEvents(cursor = 0): Promise<{
  events: SyncEvent[];
  nextCursor: number;
  workspaceId: string | null;
}> {
  const events: SyncEvent[] = [];
  let nextCursor = cursor;
  let workspaceId: string | null = null;

  for (let page = 0; page < 100; page += 1) {
    const response = await fetch(`/api/sync/events?cursor=${nextCursor}`, {
      headers: { accept: "application/json" },
    });
    const payload = (await response.json()) as {
      workspaceId?: string;
      events?: SyncEvent[];
      nextCursor?: number;
      hasMore?: boolean;
      error?: string;
    };
    if (!response.ok || !payload.events) {
      throw new Error(payload.error ?? "Cloud synchronization failed.");
    }
    if (payload.workspaceId) {
      if (workspaceId && workspaceId !== payload.workspaceId) {
        throw new Error("Cloud workspace identity changed during synchronization.");
      }
      workspaceId = payload.workspaceId;
    }
    events.push(...payload.events);
    const candidateCursor = payload.nextCursor ?? nextCursor;
    if (!payload.hasMore) {
      return { events, nextCursor: candidateCursor, workspaceId };
    }
    if (candidateCursor <= nextCursor) {
      throw new Error("Cloud synchronization cursor did not advance.");
    }
    nextCursor = candidateCursor;
  }

  throw new Error("Cloud synchronization exceeded the safe pagination limit.");
}

export async function decryptLatestEntities(
  rawKey: string,
  events: SyncEvent[],
): Promise<Map<string, DecryptedEntity>> {
  const latest = new Map<string, SyncEvent>();
  for (const event of events) {
    const key = `${event.entityType}:${event.entityId}`;
    if ((latest.get(key)?.sequence ?? -1) < event.sequence)
      latest.set(key, event);
  }
  const decrypted = new Map<string, DecryptedEntity>();
  await Promise.all(
    Array.from(latest.entries()).map(async ([key, event]) => {
      decrypted.set(key, {
        event,
        value: await decryptJson(rawKey, event.payloadCiphertext),
        version: event.baseVersion + 1,
      });
    }),
  );
  return decrypted;
}

export async function putEncryptedEntity(input: {
  rawKey: string;
  entityType: string;
  entityId: string;
  baseVersion: number;
  value: unknown;
}): Promise<number> {
  const payloadCiphertext = await encryptJson(input.rawKey, input.value);
  const response = await fetch("/api/sync/events", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      id: `evt-${crypto.randomUUID()}`,
      correlationId: `cor-${crypto.randomUUID()}`,
      entityType: input.entityType,
      entityId: input.entityId,
      baseVersion: input.baseVersion,
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
      `This record changed on another device. Refresh before saving again (cloud version ${payload.conflict?.expectedVersion ?? "unknown"}).`,
    );
  }
  if (!response.ok) {
    throw new Error(payload.error ?? "Encrypted record could not be saved.");
  }
  const expectedVersion = input.baseVersion + 1;
  if (payload.event?.version !== expectedVersion) {
    throw new Error(
      "Encrypted record was not acknowledged at the expected version.",
    );
  }
  return expectedVersion;
}

export async function uploadEncryptedResume(
  rawKey: string,
  file: File,
): Promise<ResumeRecord> {
  if (file.size === 0 || file.size > 12 * 1024 * 1024) {
    throw new Error("Choose a résumé file between 1 byte and 12 MB.");
  }
  const objectId = `obj-${crypto.randomUUID()}`;
  const record: ResumeRecord = {
    resumeId: `resume-${crypto.randomUUID()}`,
    objectId,
    name: file.name,
    contentType: file.type || "application/octet-stream",
    sizeBytes: file.size,
    addedAt: new Date().toISOString(),
  };
  const encryptedPayload = await encryptBytes(
    rawKey,
    new Uint8Array(await file.arrayBuffer()),
  );
  const metadataCiphertext = await encryptJson(rawKey, record);
  const bytes = new TextEncoder().encode(encryptedPayload);
  const response = await fetch("/api/objects", {
    method: "POST",
    headers: {
      "content-type": "application/octet-stream",
      "x-munshi-object-id": objectId,
      "x-munshi-purpose": "RESUME",
      "x-munshi-metadata-ciphertext": metadataCiphertext,
      "x-munshi-wrapped-key": "workspace-key-v1",
      "x-munshi-payload-sha256": await sha256Hex(bytes.buffer),
    },
    body: bytes,
  });
  const payload = (await response.json()) as { error?: string };
  if (!response.ok) {
    throw new Error(payload.error ?? "Encrypted résumé upload failed.");
  }
  return record;
}

export async function listEncryptedResumes(
  rawKey: string,
): Promise<ResumeRecord[]> {
  const response = await fetch("/api/objects", {
    headers: { accept: "application/json" },
  });
  const payload = (await response.json()) as {
    objects?: Array<{ purpose: string; metadataCiphertext: string }>;
    error?: string;
  };
  if (!response.ok || !payload.objects) {
    throw new Error(payload.error ?? "Encrypted résumés could not be loaded.");
  }
  const records = await Promise.all(
    payload.objects
      .filter((object) => object.purpose === "RESUME")
      .map((object) =>
        decryptJson<ResumeRecord>(rawKey, object.metadataCiphertext),
      ),
  );
  return records.sort((left, right) =>
    right.addedAt.localeCompare(left.addedAt),
  );
}

export async function downloadEncryptedResume(
  rawKey: string,
  record: ResumeRecord,
): Promise<void> {
  const response = await fetch(
    `/api/objects/${encodeURIComponent(record.objectId)}`,
    {
      headers: { accept: "application/octet-stream" },
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
    };
    throw new Error(payload.error ?? "Encrypted résumé download failed.");
  }
  const encryptedEnvelope = new TextDecoder().decode(
    new Uint8Array(await response.arrayBuffer()),
  );
  const plaintext = await decryptBytes(rawKey, encryptedEnvelope);
  const url = URL.createObjectURL(
    new Blob([plaintext.buffer], { type: record.contentType }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = record.name;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
