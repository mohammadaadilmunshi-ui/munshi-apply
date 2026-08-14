import type { MasterProfile } from "@munshi-apply/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";
import { saveProfile } from "./client";

function profile(displayName: string, updatedAt: string): MasterProfile {
  return {
    profileId: "profile-test",
    displayName,
    facts: [],
    createdAt: "2026-08-14T00:00:00.000Z",
    updatedAt,
    schemaVersion: 1,
  };
}

describe("profile save queue", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("coalesces rapid edits and resolves only after the newest save finishes", async () => {
    const responders: Array<(value: unknown) => void> = [];
    const sendMessage = vi.fn(
      (_request: unknown) =>
        new Promise<unknown>((resolve) => {
          responders.push(resolve);
        }),
    );
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const first = saveProfile(profile("first", "2026-08-14T12:00:00.000Z"));
    const second = saveProfile(profile("newest", "2026-08-14T12:00:01.000Z"));

    expect(sendMessage).toHaveBeenCalledTimes(1);
    responders[0]?.({ ok: true });

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

    responders[1]?.({ ok: true });
    await Promise.all([first, second]);
    expect(firstResolved).toBe(true);
  });
});
