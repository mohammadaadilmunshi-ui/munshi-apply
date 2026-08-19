import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { afterEach, describe, expect, it, vi } from "vitest";
import { saveProfile } from "./client";

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
});
