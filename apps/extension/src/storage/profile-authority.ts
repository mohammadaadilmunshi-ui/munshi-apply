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
  let browser: ProfileSnapshot | null = null;
  let browserError: unknown = null;
  try {
    browser = await stores.getBrowser();
  } catch (error) {
    browserError = error;
  }

  let native: ProfileSnapshot | null = null;
  let nativeError: unknown = null;
  try {
    native = await stores.getNative();
  } catch (error) {
    nativeError = error;
  }

  if (browserError) {
    if (native) return native;
    const reason =
      browserError instanceof Error
        ? browserError.message
        : String(browserError);
    throw new Error(
      `Browser profile vault is unreadable and no native recovery snapshot is available: ${reason}`,
    );
  }

  if (nativeError) {
    return browser;
  }

  if (!native && !browser) return null;
  if (!native && browser) {
    try {
      await stores.saveNative(browser);
    } catch {
      // Loading a known-good browser snapshot must not fail because a mirror
      // write is temporarily unavailable.
    }
    return browser;
  }
  if (native && !browser) {
    try {
      await stores.saveBrowser(native);
    } catch {
      // Preserve the authoritative native value even when the browser mirror
      // cannot be repaired immediately.
    }
    return native;
  }

  const reconciled = reconcileProtectedProfile(browser!, native!);
  if (!sameSnapshot(reconciled, native)) {
    try {
      await stores.saveNative(reconciled);
    } catch {
      // Reconciliation remains readable even if a mirror update must retry later.
    }
  }
  if (!sameSnapshot(reconciled, browser)) {
    try {
      await stores.saveBrowser(reconciled);
    } catch {
      // Reconciliation remains readable even if a mirror update must retry later.
    }
  }
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
