import {
  ApplicationPageSchema,
  type ApplicationPage,
} from "@munshi-apply/contracts";
import { isEligibleApplicationPage } from "@munshi-apply/application-model";
import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";

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
  workspaceId: string | null;
  vaultFingerprint: string | null;
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
  sha256?: string;
  family?: string;
  version?: number;
  source?: "MASTER" | "TAILORED" | "IMPORTED";
  roleFamily?: string | null;
  active?: boolean;
  deletedAt?: string;
};

export type ApplicationReview = {
  reviewId: string;
  pageId: string;
  resumeId: string | null;
  resumeSha256?: string | null;
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
  profile: ProfileSnapshot | null;
  profileVersion: number;
  applications: ApplicationPage[];
  reviews: ApplicationReview[];
  resumes: ResumeRecord[];
  nextCursor: number;
  workspaceId: string | null;
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
const DEFAULT_CLOUD_REQUEST_TIMEOUT_MS = 5_000;
const CLOUD_WRITE_TIMEOUT_MS = 8_000;
const CLOUD_UPLOAD_TIMEOUT_MS = 20_000;

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMilliseconds = DEFAULT_CLOUD_REQUEST_TIMEOUT_MS,
  timeoutMessage = "Encrypted workspace request timed out",
): Promise<Response> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(
    () => controller.abort(),
    Math.max(1, timeoutMilliseconds),
  );
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) throw new Error(timeoutMessage);
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

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

function sameOrigin(left: string, right: string): boolean {
  try {
    return new URL(left).origin === new URL(right).origin;
  } catch {
    return false;
  }
}

export function parseCloudApplicationPage(
  value: unknown,
): ApplicationPage | null {
  const parsed = ApplicationPageSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function shouldPublishApplicationSnapshot(
  connection: CloudConnection,
  page: ApplicationPage,
): boolean {
  return (
    !sameOrigin(connection.baseUrl, page.url) && isEligibleApplicationPage(page)
  );
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

  const response = await fetchWithTimeout(
    `${baseUrl}/api/device-enrollment`,
    {
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
    },
    10_000,
    "Device enrollment timed out after 10 seconds",
  );
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

let cloudHealthInFlight: Promise<CloudHealth> | null = null;

export function getCloudHealth(
  connection: CloudConnection,
): Promise<CloudHealth> {
  if (cloudHealthInFlight) return cloudHealthInFlight;
  const operation = (async (): Promise<CloudHealth> => {
    const response = await fetchWithTimeout(
      `${connection.baseUrl}/api/sync/events?cursor=0`,
      {
        headers: {
          accept: "application/json",
          authorization: `Bearer ${connection.credential}`,
        },
      },
      5_000,
      "Encrypted workspace check timed out. Local profile data remains protected.",
    );
    const payload = (await response.json()) as {
      workspaceId?: string;
      nextCursor?: number;
      error?: string;
    };
    if (!response.ok) {
      throw new Error(payload.error ?? "Cloud health check failed");
    }
    const rawKey = await getWorkspaceEncryptionKey();
    return {
      connected: true,
      baseUrl: connection.baseUrl,
      deviceId: connection.deviceId,
      workspaceId: payload.workspaceId ?? null,
      vaultFingerprint: rawKey ? (await sha256Hex(rawKey)).slice(0, 16) : null,
      nextCursor: payload.nextCursor ?? 0,
      encryptionReady: rawKey !== null,
    };
  })();
  cloudHealthInFlight = operation;
  void operation.then(
    () => {
      if (cloudHealthInFlight === operation) cloudHealthInFlight = null;
    },
    () => {
      if (cloudHealthInFlight === operation) cloudHealthInFlight = null;
    },
  );
  return operation;
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
  const response = await fetchWithTimeout(
    `${connection.baseUrl}/api/device-encryption`,
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${connection.credential}`,
      },
      body: JSON.stringify({
        challengeId: bundle.challengeId,
        secret: bundle.secret,
      }),
    },
    10_000,
    "Encrypted synchronization activation timed out after 10 seconds",
  );
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
): Promise<{
  events: CloudSyncEvent[];
  nextCursor: number;
  workspaceId: string | null;
}> {
  const events: CloudSyncEvent[] = [];
  let nextCursor = cursor;
  let workspaceId: string | null = null;

  for (let page = 0; page < 100; page += 1) {
    const response = await fetchWithTimeout(
      `${connection.baseUrl}/api/sync/events?cursor=${nextCursor}`,
      {
        headers: {
          accept: "application/json",
          authorization: `Bearer ${connection.credential}`,
        },
      },
      DEFAULT_CLOUD_REQUEST_TIMEOUT_MS,
      "Encrypted workspace event download timed out after 5 seconds",
    );
    const payload = (await response.json()) as {
      workspaceId?: string;
      events?: CloudSyncEvent[];
      nextCursor?: number;
      hasMore?: boolean;
      error?: string;
    };
    if (!response.ok || !payload.events) {
      throw new Error(payload.error ?? "Cloud event download failed");
    }
    if (payload.workspaceId) {
      if (workspaceId && workspaceId !== payload.workspaceId) {
        throw new Error(
          "Cloud workspace identity changed during synchronization",
        );
      }
      workspaceId = payload.workspaceId;
    }
    events.push(...payload.events);
    const candidateCursor = payload.nextCursor ?? nextCursor;
    if (!payload.hasMore) {
      return { events, nextCursor: candidateCursor, workspaceId };
    }
    if (candidateCursor <= nextCursor) {
      throw new Error("Cloud synchronization cursor did not advance");
    }
    nextCursor = candidateCursor;
  }

  throw new Error("Cloud synchronization exceeded the safe pagination limit");
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

export async function postEncryptedEntity(input: {
  connection: CloudConnection;
  rawKey: string;
  entityType: string;
  entityId: string;
  baseVersion: number;
  value: unknown;
}): Promise<number> {
  const payloadCiphertext = await encryptJson(input.rawKey, input.value);
  const response = await fetchWithTimeout(
    `${input.connection.baseUrl}/api/sync/events`,
    {
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
    },
    CLOUD_WRITE_TIMEOUT_MS,
    "Encrypted workspace update timed out after 8 seconds",
  );
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
  const expectedVersion = input.baseVersion + 1;
  if (payload.event?.version !== expectedVersion) {
    throw new Error(
      "Encrypted cloud update was not acknowledged at the expected version",
    );
  }
  return expectedVersion;
}

let cloudSnapshotInFlight: Promise<CloudSnapshot> | null = null;

export function getCloudSnapshot(
  connection: CloudConnection,
): Promise<CloudSnapshot> {
  if (cloudSnapshotInFlight) return cloudSnapshotInFlight;
  const operation = (async (): Promise<CloudSnapshot> => {
    const rawKey = await getWorkspaceEncryptionKey();
    if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
    const { events, nextCursor, workspaceId } = await fetchCloudEvents(
      connection,
      0,
    );
    const latest = latestEvents(events);
    let profile: ProfileSnapshot | null = null;
    let profileVersion = 0;
    const applications: ApplicationPage[] = [];
    const reviews: ApplicationReview[] = [];
    const resumes: ResumeRecord[] = [];
    for (const event of latest.values()) {
      if (event.entityType === "PROFILE.V1") {
        profile = parseProfileSnapshot(
          await decryptJson<unknown>(rawKey, event.payloadCiphertext),
        );
        profileVersion = event.baseVersion + 1;
      } else if (event.entityType === "APPLICATION.V1") {
        const application = parseCloudApplicationPage(
          await decryptJson<unknown>(rawKey, event.payloadCiphertext),
        );
        if (
          application &&
          shouldPublishApplicationSnapshot(connection, application)
        ) {
          applications.push(application);
        }
      } else if (event.entityType === "APPLICATION.REVIEW.V1") {
        reviews.push(
          await decryptJson<ApplicationReview>(rawKey, event.payloadCiphertext),
        );
      } else if (event.entityType === "RESUME.V1") {
        const resume = await decryptJson<ResumeRecord>(
          rawKey,
          event.payloadCiphertext,
        );
        if (!resume.deletedAt) resumes.push(resume);
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
      workspaceId,
    };
  })();
  cloudSnapshotInFlight = operation;
  void operation.then(
    () => {
      if (cloudSnapshotInFlight === operation) cloudSnapshotInFlight = null;
    },
    () => {
      if (cloudSnapshotInFlight === operation) cloudSnapshotInFlight = null;
    },
  );
  return operation;
}

export async function publishApplicationSnapshot(
  connection: CloudConnection,
  page: ApplicationPage,
): Promise<void> {
  if (!shouldPublishApplicationSnapshot(connection, page)) return;
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

async function publishApplicationReviewRemote(
  connection: CloudConnection,
  rawKey: string,
  review: ApplicationReview,
): Promise<void> {
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

export async function publishApplicationReview(
  connection: CloudConnection,
  review: ApplicationReview,
): Promise<void> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");

  // Review attribution is important, but it must never sit in front of an
  // employer-page action. Network work is bounded and intentionally detached
  // from the fill critical path; the next cloud reconciliation can recover the
  // canonical application state even if this best-effort publish is unavailable.
  void publishApplicationReviewRemote(connection, rawKey, review).catch(
    () => undefined,
  );
}

const allowedResumeExtensions = new Set(["pdf", "doc", "docx"]);
const allowedResumeContentTypes = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

export function validateResumeFile(
  file: Pick<File, "name" | "size" | "type">,
): void {
  if (file.size === 0 || file.size > 12 * 1024 * 1024) {
    throw new Error("Choose a résumé file between 1 byte and 12 MB");
  }
  const extension = file.name.toLowerCase().split(".").pop() ?? "";
  if (!allowedResumeExtensions.has(extension)) {
    throw new Error("Résumé must be a PDF, DOC, or DOCX file");
  }
  if (file.type && !allowedResumeContentTypes.has(file.type.toLowerCase())) {
    throw new Error("Résumé file type does not match PDF, DOC, or DOCX");
  }
}

export async function uploadEncryptedResume(
  connection: CloudConnection,
  file: File,
  options: {
    family?: string;
    source?: "MASTER" | "TAILORED" | "IMPORTED";
    roleFamily?: string | null;
  } = {},
): Promise<ResumeRecord> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  validateResumeFile(file);

  const family = options.family?.trim() || "master";
  const { events: resumeEvents } = await fetchCloudEvents(connection, 0);
  const resumeHistory: ResumeRecord[] = [];
  for (const event of latestEvents(resumeEvents).values()) {
    if (event.entityType !== "RESUME.V1") continue;
    resumeHistory.push(
      await decryptJson<ResumeRecord>(rawKey, event.payloadCiphertext),
    );
  }
  const version =
    Math.max(
      0,
      ...resumeHistory
        .filter((resume) => (resume.family ?? "master") === family)
        .map((resume) => resume.version ?? 1),
    ) + 1;
  const fileBuffer = await file.arrayBuffer();
  const fileSha256 = await sha256Hex(fileBuffer);
  const objectId = `obj-${crypto.randomUUID()}`;
  const record: ResumeRecord = {
    resumeId: `resume-${crypto.randomUUID()}`,
    objectId,
    name: file.name,
    contentType: file.type || "application/octet-stream",
    sizeBytes: file.size,
    addedAt: new Date().toISOString(),
    sha256: fileSha256,
    family,
    version,
    source: options.source ?? "IMPORTED",
    roleFamily: options.roleFamily ?? null,
    active: true,
  };
  const encryptedPayload = await encryptBytes(
    rawKey,
    new Uint8Array(fileBuffer),
  );
  const bytes = new TextEncoder().encode(encryptedPayload);
  const metadataCiphertext = await encryptJson(rawKey, record);
  const response = await fetchWithTimeout(
    `${connection.baseUrl}/api/objects`,
    {
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
    },
    CLOUD_UPLOAD_TIMEOUT_MS,
    "Encrypted résumé upload timed out after 20 seconds",
  );
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
