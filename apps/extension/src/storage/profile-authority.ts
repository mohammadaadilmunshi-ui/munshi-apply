import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";
import {
  getNativeProfileSnapshot,
  saveNativeProfileSnapshot,
} from "../messaging/native";
import { reconcileProtectedProfile } from "./profile-sync";
import { getProfile, saveProfile } from "./vault";

export type ProfileSnapshotStores = {
  getBrowser: () => Promise<ProfileSnapshot | null>;
  saveBrowser: (snapshot: ProfileSnapshot) => Promise<void>;
  getNative: () => Promise<ProfileSnapshot | null>;
  saveNative: (snapshot: ProfileSnapshot) => Promise<void>;
};

const defaultStores: ProfileSnapshotStores = {
  getBrowser: getProfile,
  saveBrowser: saveProfile,
  getNative: getNativeProfileSnapshot,
  saveNative: saveNativeProfileSnapshot,
};

function sameSnapshot(
  left: ProfileSnapshot | null,
  right: ProfileSnapshot | null,
): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

/**
 * Load the desktop snapshot with SQLite as the durable local authority when
 * Native Messaging is healthy. IndexedDB is a browser mirror and the fallback
 * when native is unavailable.
 */
export async function loadAuthoritativeProfileSnapshot(
  stores: ProfileSnapshotStores = defaultStores,
): Promise<ProfileSnapshot | null> {
  const browser = await stores.getBrowser();
  let native: ProfileSnapshot | null;
  try {
    native = await stores.getNative();
  } catch {
    return browser;
  }

  if (!native && !browser) return null;
  if (!native && browser) {
    await stores.saveNative(browser);
    return browser;
  }
  if (native && !browser) {
    await stores.saveBrowser(native);
    return native;
  }

  const reconciled = reconcileProtectedProfile(browser!, native!);
  if (!sameSnapshot(reconciled, native)) await stores.saveNative(reconciled);
  if (!sameSnapshot(reconciled, browser)) await stores.saveBrowser(reconciled);
  return reconciled;
}

export async function persistAuthoritativeProfileSnapshot(
  snapshot: ProfileSnapshot,
  stores: ProfileSnapshotStores = defaultStores,
): Promise<{ nativeAvailable: boolean }> {
  const parsed = parseProfileSnapshot(snapshot);
  let nativeAvailable = true;
  try {
    await stores.saveNative(parsed);
  } catch {
    nativeAvailable = false;
  }
  await stores.saveBrowser(parsed);
  return { nativeAvailable };
}
