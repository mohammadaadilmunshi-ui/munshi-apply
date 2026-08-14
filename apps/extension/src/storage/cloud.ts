import type { ApplicationPage, MasterProfile } from "@munshi-apply/contracts";

export type CloudConnection = {
  baseUrl: string;
  deviceId: string;
  credential: string;
  platform: string;
  connectedAt: string;
};

export type CloudHealth = {
  connected: true;
  baseUrl: string;
  deviceId: string;
  nextCursor: number;
  encryptionReady: boolean;
};

type PairingBundle = {
  challengeId: string;
  secret: string;
  workspaceKey: string | null;
  encryptionVersion: number | null;
};

export type CloudSyncEvent = {
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

export type ResumeRecord = {
  resumeId: string;
  objectId: string;
  name: string;
  contentType: string;
  sizeBytes: number;
  addedAt: string;
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

export type CloudSnapshot = {
  profile: MasterProfile | null;
  profileVersion: number;
  applications: ApplicationPage[];
  reviews: ApplicationReview[];
  resumes: ResumeRecord[];
  nextCursor: number;
};

type CipherEnvelope = {
  v: 1;
  alg: "A256GCM";
  iv: string;
  ciphertext: string;
};

const databaseName = "munshi-apply-cloud";
const databaseVersion = 1;
const settingsStore = "settings";
const keysStore = "keys";
const connectionKey = "connection";
const devicePrivateKey = "device-private-key";
const workspaceEncryptionKey = "workspace-encryption-key-v1";

function openCloudVault(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, databaseVersion);
    request.onerror = () =>
      reject(request.error ?? new Error("Cloud vault open failed"));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(settingsStore)) {
        database.createObjectStore(settingsStore);
      }
      if (!database.objectStoreNames.contains(keysStore)) {
        database.createObjectStore(keysStore);
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function read(storeName: string, key: IDBValidKey): Promise<unknown> {
  const database = await openCloudVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, "readonly");
    const request = transaction.objectStore(storeName).get(key);
    request.onerror = () =>
      reject(request.error ?? new Error("Cloud vault read failed"));
    request.onsuccess = () => resolve(request.result);
    transaction.oncomplete = () => database.close();
  });
}

async function write(
  storeName: string,
  key: IDBValidKey,
  value: unknown,
): Promise<void> {
  const database = await openCloudVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).put(value, key);
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Cloud vault write failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}

async function clear(storeName: string): Promise<void> {
  const database = await openCloudVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).clear();
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Cloud vault clear failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}

function base64Url(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function decodeBase64Url(value: string): Uint8Array<ArrayBuffer> {
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
    throw new Error("Pairing code does not contain a valid encryption key");
  }
  if (decodeBase64Url(value).byteLength !== 32) {
    throw new Error("Pairing code does not contain a valid encryption key");
  }
  return value;
}

export function parsePairingBundle(value: string): PairingBundle {
  let candidate: unknown;
  try {
    candidate = JSON.parse(value);
  } catch {
    throw new Error("Pairing bundle is not valid JSON");
  }
  if (
    !candidate ||
    typeof candidate !== "object" ||
    !("challengeId" in candidate) ||
    !("secret" in candidate) ||
    typeof candidate.challengeId !== "string" ||
    typeof candidate.secret !== "string" ||
    candidate.challengeId.length < 8 ||
    candidate.secret.length < 32
  ) {
    throw new Error("Pairing bundle is incomplete");
  }
  return {
    challengeId: candidate.challengeId,
    secret: candidate.secret,
    workspaceKey:
      "workspaceKey" in candidate && typeof candidate.workspaceKey === "string"
        ? validateWorkspaceKey(candidate.workspaceKey)
        : null,
    encryptionVersion:
      "encryptionVersion" in candidate &&
      typeof candidate.encryptionVersion === "number"
        ? candidate.encryptionVersion
        : null,
  };
}

export function normalizeBaseUrl(value: string): string {
  const url = new URL(value.trim());
  if (url.protocol !== "https:") {
    throw new Error("Workspace URL must use HTTPS");
  }
  url.pathname = "/";
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/$/, "");
}

export async function getCloudConnection(): Promise<CloudConnection | null> {
  const candidate = await read(settingsStore, connectionKey);
  if (!candidate || typeof candidate !== "object") return null;
  const connection = candidate as Partial<CloudConnection>;
  if (
    !connection.baseUrl ||
    !connection.deviceId ||
    !connection.credential ||
    !connection.platform ||
    !connection.connectedAt
  ) {
    return null;
  }
  return connection as CloudConnection;
}

export async function enrollCloudDevice(input: {
  baseUrl: string;
  pairingBundle: string;
  platform: string;
}): Promise<CloudConnection> {
  const baseUrl = normalizeBaseUrl(input.baseUrl);
  const bundle = parsePairingBundle(input.pairingBundle);
  const deviceId = crypto.randomUUID();
  const keyPair = (await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign", "verify"],
  )) as CryptoKeyPair;
  const publicKeyJwk = await crypto.subtle.exportKey("jwk", keyPair.publicKey);
  const message = new TextEncoder().encode(
    `munshi-enroll\n${bundle.challengeId}\n${bundle.secret}\n${deviceId}`,
  );
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    keyPair.privateKey,
    message,
  );
  const randomLabel = crypto.getRandomValues(new Uint8Array(32));

  const response = await fetch(`${baseUrl}/api/device-enrollment`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      challengeId: bundle.challengeId,
      secret: bundle.secret,
      deviceId,
      labelCiphertext: base64Url(randomLabel),
      platform: input.platform,
      publicKeyJwk,
      signature: base64Url(signature),
    }),
  });
  const payload = (await response.json()) as {
    credential?: string;
    error?: string;
  };
  if (!response.ok || !payload.credential) {
    throw new Error(payload.error ?? "Device enrollment failed");
  }

  const connection: CloudConnection = {
    baseUrl,
    deviceId,
    credential: payload.credential,
    platform: input.platform,
    connectedAt: new Date().toISOString(),
  };
  await Promise.all([
    write(keysStore, devicePrivateKey, keyPair.privateKey),
    write(settingsStore, connectionKey, connection),
    bundle.workspaceKey
      ? write(keysStore, workspaceEncryptionKey, bundle.workspaceKey)
      : Promise.resolve(),
  ]);
  return connection;
}

export async function getCloudHealth(
  connection: CloudConnection,
): Promise<CloudHealth> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(
      `${connection.baseUrl}/api/sync/events?cursor=0`,
      {
        headers: {
          accept: "application/json",
          authorization: `Bearer ${connection.credential}`,
        },
        signal: controller.signal,
      },
    );
    const payload = (await response.json()) as {
      nextCursor?: number;
      error?: string;
    };
    if (!response.ok) {
      throw new Error(payload.error ?? "Cloud health check failed");
    }
    return {
      connected: true,
      baseUrl: connection.baseUrl,
      deviceId: connection.deviceId,
      nextCursor: payload.nextCursor ?? 0,
      encryptionReady: await isCloudEncryptionReady(),
    };
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export async function getWorkspaceEncryptionKey(): Promise<string | null> {
  const value = await read(keysStore, workspaceEncryptionKey);
  if (value === undefined) return null;
  return validateWorkspaceKey(value);
}

export async function isCloudEncryptionReady(): Promise<boolean> {
  return (await getWorkspaceEncryptionKey()) !== null;
}

export async function activateCloudEncryption(
  connection: CloudConnection,
  pairingBundle: string,
): Promise<void> {
  const bundle = parsePairingBundle(pairingBundle);
  if (!bundle.workspaceKey || bundle.encryptionVersion !== 1) {
    throw new Error(
      "Create a new code from the updated private workspace to enable encrypted sync",
    );
  }
  const response = await fetch(`${connection.baseUrl}/api/device-encryption`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${connection.credential}`,
    },
    body: JSON.stringify({
      challengeId: bundle.challengeId,
      secret: bundle.secret,
    }),
  });
  const payload = (await response.json()) as { error?: string };
  if (!response.ok) {
    throw new Error(
      payload.error ?? "Encrypted synchronization activation failed",
    );
  }
  await write(keysStore, workspaceEncryptionKey, bundle.workspaceKey);
}

async function importAesKey(rawKey: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    decodeBase64Url(validateWorkspaceKey(rawKey)),
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
    iv: base64Url(iv),
    ciphertext: base64Url(ciphertext),
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
    throw new Error("Encrypted cloud payload is invalid");
  }
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: decodeBase64Url(envelope.iv) },
    await importAesKey(rawKey),
    decodeBase64Url(envelope.ciphertext),
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

export async function fetchCloudEvents(
  connection: CloudConnection,
  cursor = 0,
): Promise<{ events: CloudSyncEvent[]; nextCursor: number }> {
  const response = await fetch(
    `${connection.baseUrl}/api/sync/events?cursor=${cursor}`,
    {
      headers: {
        accept: "application/json",
        authorization: `Bearer ${connection.credential}`,
      },
    },
  );
  const payload = (await response.json()) as {
    events?: CloudSyncEvent[];
    nextCursor?: number;
    error?: string;
  };
  if (!response.ok || !payload.events) {
    throw new Error(payload.error ?? "Cloud event download failed");
  }
  return { events: payload.events, nextCursor: payload.nextCursor ?? cursor };
}

function latestEvents(events: CloudSyncEvent[]): Map<string, CloudSyncEvent> {
  const latest = new Map<string, CloudSyncEvent>();
  for (const event of events) {
    const key = `${event.entityType}:${event.entityId}`;
    if ((latest.get(key)?.sequence ?? -1) < event.sequence)
      latest.set(key, event);
  }
  return latest;
}

async function postEncryptedEntity(input: {
  connection: CloudConnection;
  rawKey: string;
  entityType: string;
  entityId: string;
  baseVersion: number;
  value: unknown;
}): Promise<number> {
  const payloadCiphertext = await encryptJson(input.rawKey, input.value);
  const response = await fetch(`${input.connection.baseUrl}/api/sync/events`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${input.connection.credential}`,
    },
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
      `Cloud record changed on another device (version ${payload.conflict?.expectedVersion ?? "unknown"})`,
    );
  }
  if (!response.ok) {
    throw new Error(payload.error ?? "Encrypted cloud update failed");
  }
  return payload.event?.version ?? input.baseVersion + 1;
}

export async function getCloudSnapshot(
  connection: CloudConnection,
): Promise<CloudSnapshot> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  const { events, nextCursor } = await fetchCloudEvents(connection, 0);
  const latest = latestEvents(events);
  let profile: MasterProfile | null = null;
  let profileVersion = 0;
  const applications: ApplicationPage[] = [];
  const reviews: ApplicationReview[] = [];
  const resumes: ResumeRecord[] = [];
  for (const event of latest.values()) {
    if (event.entityType === "PROFILE.V1") {
      profile = await decryptJson<MasterProfile>(
        rawKey,
        event.payloadCiphertext,
      );
      profileVersion = event.baseVersion + 1;
    } else if (event.entityType === "APPLICATION.V1") {
      applications.push(
        await decryptJson<ApplicationPage>(rawKey, event.payloadCiphertext),
      );
    } else if (event.entityType === "APPLICATION.REVIEW.V1") {
      reviews.push(
        await decryptJson<ApplicationReview>(rawKey, event.payloadCiphertext),
      );
    } else if (event.entityType === "RESUME.V1") {
      resumes.push(
        await decryptJson<ResumeRecord>(rawKey, event.payloadCiphertext),
      );
    }
  }
  applications.sort((left, right) =>
    right.observedAt.localeCompare(left.observedAt),
  );
  resumes.sort((left, right) => right.addedAt.localeCompare(left.addedAt));
  return {
    profile,
    profileVersion,
    applications,
    reviews,
    resumes,
    nextCursor,
  };
}

export async function synchronizeProfile(
  connection: CloudConnection,
  localProfile: MasterProfile,
): Promise<MasterProfile> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  const snapshot = await getCloudSnapshot(connection);
  if (!snapshot.profile) {
    if (localProfile.facts.length > 0) {
      await postEncryptedEntity({
        connection,
        rawKey,
        entityType: "PROFILE.V1",
        entityId: "profile-master",
        baseVersion: 0,
        value: localProfile,
      });
    }
    return localProfile;
  }
  if (localProfile.updatedAt > snapshot.profile.updatedAt) {
    await postEncryptedEntity({
      connection,
      rawKey,
      entityType: "PROFILE.V1",
      entityId: "profile-master",
      baseVersion: snapshot.profileVersion,
      value: localProfile,
    });
    return localProfile;
  }
  return snapshot.profile;
}

export async function publishApplicationSnapshot(
  connection: CloudConnection,
  page: ApplicationPage,
): Promise<void> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) return;
  const { events } = await fetchCloudEvents(connection, 0);
  const latest = latestEvents(events).get(`APPLICATION.V1:${page.pageId}`);
  if (latest) {
    const existing = await decryptJson<ApplicationPage>(
      rawKey,
      latest.payloadCiphertext,
    );
    if (
      existing.observedAt === page.observedAt ||
      JSON.stringify(existing.questions) === JSON.stringify(page.questions)
    ) {
      return;
    }
  }
  await postEncryptedEntity({
    connection,
    rawKey,
    entityType: "APPLICATION.V1",
    entityId: page.pageId,
    baseVersion: latest ? latest.baseVersion + 1 : 0,
    value: page,
  });
}

export async function publishApplicationReview(
  connection: CloudConnection,
  review: ApplicationReview,
): Promise<void> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  const { events } = await fetchCloudEvents(connection, 0);
  const latest = latestEvents(events).get(
    `APPLICATION.REVIEW.V1:${review.reviewId}`,
  );
  await postEncryptedEntity({
    connection,
    rawKey,
    entityType: "APPLICATION.REVIEW.V1",
    entityId: review.reviewId,
    baseVersion: latest ? latest.baseVersion + 1 : 0,
    value: review,
  });
}

export async function uploadEncryptedResume(
  connection: CloudConnection,
  file: File,
): Promise<ResumeRecord> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  if (file.size === 0 || file.size > 12 * 1024 * 1024) {
    throw new Error("Choose a résumé file between 1 byte and 12 MB");
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
  const bytes = new TextEncoder().encode(encryptedPayload);
  const metadataCiphertext = await encryptJson(rawKey, record);
  const response = await fetch(`${connection.baseUrl}/api/objects`, {
    method: "POST",
    headers: {
      "content-type": "application/octet-stream",
      authorization: `Bearer ${connection.credential}`,
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
    throw new Error(payload.error ?? "Encrypted résumé upload failed");
  }
  await postEncryptedEntity({
    connection,
    rawKey,
    entityType: "RESUME.V1",
    entityId: record.resumeId,
    baseVersion: 0,
    value: record,
  });
  return record;
}

export async function disconnectCloud(): Promise<void> {
  await Promise.all([clear(settingsStore), clear(keysStore)]);
}
