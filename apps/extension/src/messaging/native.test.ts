import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const timestamp = "2026-08-14T18:00:00.000Z";

function profile(): ProfileSnapshot {
  return {
    profileId: "profile-1",
    displayName: "Test profile",
    facts: [],
    records: [],
    recordTombstones: [],
    createdAt: timestamp,
    updatedAt: timestamp,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

function installNativePort(response: unknown) {
  const messageListeners: Array<(value: unknown) => void> = [];
  const disconnectListeners: Array<() => void> = [];
  const port = {
    postMessage: vi.fn(() => {
      queueMicrotask(() => {
        for (const listener of messageListeners) listener(response);
      });
    }),
    disconnect: vi.fn(() => {
      for (const listener of disconnectListeners) listener();
    }),
    onMessage: {
      addListener: (listener: (value: unknown) => void) =>
        messageListeners.push(listener),
    },
    onDisconnect: {
      addListener: (listener: () => void) => disconnectListeners.push(listener),
    },
  };
  const connectNative = vi.fn(() => port);
  vi.stubGlobal("chrome", {
    runtime: { connectNative, lastError: undefined },
  });
  return { connectNative, port };
}

async function nativeModule() {
  return import("./native");
}

describe("native profile snapshot messages", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads and validates the canonical snapshot", async () => {
    const native = installNativePort({ ok: true, data: profile() });
    const { getNativeProfileSnapshot } = await nativeModule();

    await expect(getNativeProfileSnapshot()).resolves.toEqual(profile());
    expect(native.connectNative).toHaveBeenCalledWith("systems.munshi.apply");
    expect(native.port.postMessage).toHaveBeenCalledWith({
      type: "GET_PROFILE_SNAPSHOT",
    });
  });

  it("rejects malformed native profile data", async () => {
    installNativePort({ ok: true, data: { profileId: "incomplete" } });
    const { getNativeProfileSnapshot } = await nativeModule();

    await expect(getNativeProfileSnapshot()).rejects.toThrow();
  });

  it("validates before saving and sends the canonical message", async () => {
    const native = installNativePort({ ok: true, data: { saved: true } });
    const { saveNativeProfileSnapshot } = await nativeModule();

    await saveNativeProfileSnapshot(profile());
    expect(native.port.postMessage).toHaveBeenCalledWith({
      type: "SAVE_PROFILE_SNAPSHOT",
      payload: profile(),
    });
  });
});
