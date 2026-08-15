import {
  ApplicationPageSchema,
  type ApplicationPage,
} from "@munshi-apply/contracts";
import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";

const databaseName = "munshi-apply-vault";
const databaseVersion = 1;
const profilesStore = "profiles";
const pagesStore = "pages";
const activeProfileKey = "active";

function openVault(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, databaseVersion);
    request.onerror = () =>
      reject(request.error ?? new Error("Vault open failed"));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(profilesStore)) {
        database.createObjectStore(profilesStore);
      }
      if (!database.objectStoreNames.contains(pagesStore)) {
        database.createObjectStore(pagesStore);
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function read(storeName: string, key: IDBValidKey): Promise<unknown> {
  const database = await openVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, "readonly");
    const request = transaction.objectStore(storeName).get(key);
    request.onerror = () =>
      reject(request.error ?? new Error("Vault read failed"));
    request.onsuccess = () => resolve(request.result);
    transaction.oncomplete = () => database.close();
  });
}

async function readAll(storeName: string): Promise<unknown[]> {
  const database = await openVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, "readonly");
    const request = transaction.objectStore(storeName).getAll();
    request.onerror = () =>
      reject(request.error ?? new Error("Vault read failed"));
    request.onsuccess = () => resolve(request.result);
    transaction.oncomplete = () => database.close();
  });
}

async function write(
  storeName: string,
  key: IDBValidKey,
  value: unknown,
): Promise<void> {
  const database = await openVault();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).put(value, key);
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Vault write failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}

export async function getProfile(): Promise<ProfileSnapshot | null> {
  const candidate = await read(profilesStore, activeProfileKey);
  if (candidate === undefined) return null;
  return parseProfileSnapshot(candidate);
}

export async function saveProfile(profile: ProfileSnapshot): Promise<void> {
  await write(profilesStore, activeProfileKey, parseProfileSnapshot(profile));
}

export async function getPage(
  tabId: number,
  frameId = 0,
): Promise<ApplicationPage | null> {
  const candidate = await read(pagesStore, `${tabId}:${frameId}`);
  if (candidate === undefined) return null;
  return ApplicationPageSchema.parse(candidate);
}

export async function getPagesForTab(
  tabId: number,
): Promise<ApplicationPage[]> {
  return (await readAll(pagesStore))
    .map((candidate) => ApplicationPageSchema.parse(candidate))
    .filter((page) => page.tabId === tabId)
    .sort((left, right) => left.frameId - right.frameId);
}

export async function deletePage(
  tabId: number,
  frameId: number,
): Promise<void> {
  const database = await openVault();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(pagesStore, "readwrite");
    transaction.objectStore(pagesStore).delete(`${tabId}:${frameId}`);
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Vault page deletion failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}

export async function clearPagesForTab(tabId: number): Promise<void> {
  const database = await openVault();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(pagesStore, "readwrite");
    const request = transaction.objectStore(pagesStore).openCursor();
    request.onerror = () =>
      reject(request.error ?? new Error("Vault page cleanup failed"));
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      const page = ApplicationPageSchema.parse(cursor.value);
      if (page.tabId === tabId) cursor.delete();
      cursor.continue();
    };
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Vault page cleanup failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}

export async function getLatestPage(): Promise<ApplicationPage | null> {
  const pages = (await readAll(pagesStore)).map((candidate) =>
    ApplicationPageSchema.parse(candidate),
  );
  const topLevelPages = pages.filter((page) => page.frameId === 0);
  const candidates = topLevelPages.length > 0 ? topLevelPages : pages;
  return (
    candidates.sort((left, right) =>
      right.observedAt.localeCompare(left.observedAt),
    )[0] ?? null
  );
}

export async function savePage(page: ApplicationPage): Promise<void> {
  await write(
    pagesStore,
    `${page.tabId}:${page.frameId}`,
    ApplicationPageSchema.parse(page),
  );
}
