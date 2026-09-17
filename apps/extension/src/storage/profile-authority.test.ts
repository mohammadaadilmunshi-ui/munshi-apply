import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { describe, expect, it, vi } from "vitest";
import {
  loadAuthoritativeProfileSnapshot,
  persistAuthoritativeProfileSnapshot,
  type ProfileSnapshotStores,
} from "./profile-authority";

function snapshot(updatedAt: string, value = "Aadil"): ProfileSnapshot {
  return {
    profileId: "profile-1",
    displayName: "Profile",
    facts: [
      {
        factId: "fact-name",
        key: "preferred_name",
        value,
        category: "IDENTITY",
        trustLevel: "USER_CONFIRMED",
        source: "TEST",
        confirmedAt: updatedAt,
        updatedAt,
        protected: false,
      },
    ],
    records: [],
    recordTombstones: [],
    createdAt: "2026-08-14T10:00:00.000Z",
    updatedAt,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

function stores(input: {
  browser?: ProfileSnapshot | null;
  native?: ProfileSnapshot | null;
  browserError?: Error;
  nativeError?: Error;
}): ProfileSnapshotStores & {
  saveBrowser: ReturnType<typeof vi.fn>;
  saveNative: ReturnType<typeof vi.fn>;
} {
  return {
    getBrowser: vi.fn(async () => {
      if (input.browserError) throw input.browserError;
      return input.browser ?? null;
    }),
    saveBrowser: vi.fn(async () => undefined),
    getNative: vi.fn(async () => {
      if (input.nativeError) throw input.nativeError;
      return input.native ?? null;
    }),
    saveNative: vi.fn(async () => undefined),
  };
}

describe("desktop profile authority", () => {
  it("mirrors a newer native snapshot into IndexedDB", async () => {
    const browser = snapshot("2026-08-14T12:00:00.000Z", "Old");
    const native = snapshot("2026-08-14T12:01:00.000Z", "New");
    const adapters = stores({ browser, native });

    await expect(loadAuthoritativeProfileSnapshot(adapters)).resolves.toEqual(
      native,
    );
    expect(adapters.saveBrowser).toHaveBeenCalledWith(native);
    expect(adapters.saveNative).not.toHaveBeenCalled();
  });

  it("falls back to IndexedDB when Native Messaging is unavailable", async () => {
    const browser = snapshot("2026-08-14T12:00:00.000Z");
    const adapters = stores({
      browser,
      nativeError: new Error("Native host unavailable"),
    });

    await expect(loadAuthoritativeProfileSnapshot(adapters)).resolves.toEqual(
      browser,
    );
    expect(adapters.saveBrowser).not.toHaveBeenCalled();
  });

  it("seeds a healthy native store from an existing browser snapshot", async () => {
    const browser = snapshot("2026-08-14T12:00:00.000Z");
    const adapters = stores({ browser, native: null });

    await expect(loadAuthoritativeProfileSnapshot(adapters)).resolves.toEqual(
      browser,
    );
    expect(adapters.saveNative).toHaveBeenCalledWith(browser);
  });

  it("recovers the authoritative native snapshot when the browser mirror is unreadable", async () => {
    const native = snapshot("2026-08-14T12:01:00.000Z", "Recovered");
    const adapters = stores({
      browserError: new Error("IndexedDB profile parse failed"),
      native,
    });

    await expect(loadAuthoritativeProfileSnapshot(adapters)).resolves.toEqual(
      native,
    );
    expect(adapters.saveBrowser).not.toHaveBeenCalled();
    expect(adapters.saveNative).not.toHaveBeenCalled();
  });

  it("refuses to present an empty profile when the browser mirror is unreadable and native has no snapshot", async () => {
    const adapters = stores({
      browserError: new Error("IndexedDB profile parse failed"),
      native: null,
    });

    await expect(loadAuthoritativeProfileSnapshot(adapters)).rejects.toThrow(
      "Browser profile vault is unreadable and no native recovery snapshot is available",
    );
  });

  it("still returns a valid snapshot when a mirror repair write fails", async () => {
    const native = snapshot("2026-08-14T12:01:00.000Z", "Recovered");
    const adapters = stores({ browser: null, native });
    adapters.saveBrowser.mockRejectedValueOnce(
      new Error("IndexedDB write failed"),
    );

    await expect(loadAuthoritativeProfileSnapshot(adapters)).resolves.toEqual(
      native,
    );
  });

  it("persists to the browser fallback when the native write fails", async () => {
    const adapters = stores({});
    adapters.saveNative.mockRejectedValueOnce(new Error("Native unavailable"));
    const value = snapshot("2026-08-14T12:00:00.000Z");

    await expect(
      persistAuthoritativeProfileSnapshot(value, adapters),
    ).resolves.toEqual({ nativeAvailable: false });
    expect(adapters.saveBrowser).toHaveBeenCalledWith(value);
  });
});
