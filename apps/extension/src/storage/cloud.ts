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
};

type PairingBundle = {
  challengeId: string;
  secret: string;
};

const databaseName = "munshi-apply-cloud";
const databaseVersion = 1;
const settingsStore = "settings";
const keysStore = "keys";
const connectionKey = "connection";
const devicePrivateKey = "device-private-key";

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
  ]);
  return connection;
}

export async function getCloudHealth(
  connection: CloudConnection,
): Promise<CloudHealth> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5_000);
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
    };
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function disconnectCloud(): Promise<void> {
  await Promise.all([clear(settingsStore), clear(keysStore)]);
}
