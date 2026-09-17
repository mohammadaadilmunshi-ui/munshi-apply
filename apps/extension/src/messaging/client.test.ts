import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getHealth, getNativeHealth, saveProfile } from "./client";

function profile(displayName: string, updatedAt: string): ProfileSnapshot {
  return {
    profileId: "profile-test",
    displayName,
    facts: [],
    records: [],
    recordTombstones: [],
    createdAt: "2026-08-14T00:00:00.000Z",
    updatedAt,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

const localAck = {
  localSaved: true as const,
  cloudSynced: false,
  conflict: null,
};

const syncedAck = {
  localSaved: true as const,
  cloudSynced: true,
  conflict: null,
};

describe("profile save queue", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("returns the service-worker acknowledgement for a single save", async () => {
    const sendMessage = vi.fn().mockResolvedValue({
      ok: true,
      data: localAck,
    });
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    await expect(
      saveProfile(profile("local", "2026-08-14T12:00:00.000Z")),
    ).resolves.toEqual(localAck);
  });

  it("coalesces rapid edits and resolves only after the newest save finishes", async () => {
    const responders: Array<(value: unknown) => void> = [];
    const sendMessage = vi.fn((request: unknown) => {
      void request;
      return new Promise<unknown>((resolve) => {
        responders.push(resolve);
      });
    });
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const first = saveProfile(profile("first", "2026-08-14T12:00:00.000Z"));
    const second = saveProfile(profile("newest", "2026-08-14T12:00:01.000Z"));

    expect(sendMessage).toHaveBeenCalledTimes(1);
    responders[0]?.({ ok: true, data: localAck });

    await vi.waitFor(() => {
      expect(sendMessage).toHaveBeenCalledTimes(2);
    });

    let firstResolved = false;
    void first.then(() => {
      firstResolved = true;
    });
    await Promise.resolve();
    expect(firstResolved).toBe(false);

    expect(sendMessage.mock.calls[1]?.[0]).toMatchObject({
      type: "SAVE_PROFILE",
      payload: { displayName: "newest" },
    });

    responders[1]?.({ ok: true, data: syncedAck });
    await expect(Promise.all([first, second])).resolves.toEqual([
      syncedAck,
      syncedAck,
    ]);
    expect(firstResolved).toBe(true);
  });

  it("rejects a malformed save acknowledgement instead of assuming success", async () => {
    const sendMessage = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    await expect(
      saveProfile(profile("invalid", "2026-08-14T12:00:02.000Z")),
    ).rejects.toThrow("Profile save returned no acknowledgement");
  });

  it("retries an Edge-aborted read-only startup health request", async () => {
    vi.useFakeTimers();
    const health = {
      status: "healthy",
      version: "0.2.8",
      platform: "mac",
      mobile: false,
      capabilities: { nativeMessaging: true, sidePanel: true },
    };
    const sendMessage = vi
      .fn()
      .mockRejectedValueOnce(new Error("The user aborted a request."))
      .mockResolvedValueOnce({ ok: true, data: health });
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const pending = getHealth();
    await vi.advanceTimersByTimeAsync(120);
    await expect(pending).resolves.toEqual(health);
    expect(sendMessage).toHaveBeenCalledTimes(2);
  });

  it("bounds a native-health request so checking cannot persist forever", async () => {
    vi.useFakeTimers();
    const sendMessage = vi.fn(() => new Promise<unknown>(() => undefined));
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const pending = getNativeHealth();
    const rejection = expect(pending).rejects.toThrow(
      "Native companion health check timed out after 5 seconds",
    );
    await vi.advanceTimersByTimeAsync(5_000);
    await rejection;
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("does not retry aborted profile writes and risk duplicate saves", async () => {
    const sendMessage = vi
      .fn()
      .mockRejectedValue(new Error("The user aborted a request."));
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    await expect(
      saveProfile(profile("abort", "2026-08-14T12:00:03.000Z")),
    ).rejects.toThrow("The user aborted a request.");
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });
});
