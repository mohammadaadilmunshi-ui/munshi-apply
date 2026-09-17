import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { afterEach, describe, expect, it, vi } from "vitest";

const vaultMocks = vi.hoisted(() => ({
  getProfile: vi.fn(),
  getPagesForTab: vi.fn(),
}));

vi.mock("../storage/vault", () => ({
  getProfile: vaultMocks.getProfile,
  getPagesForTab: vaultMocks.getPagesForTab,
}));

vi.mock("../background/page-merge", () => ({
  mergeApplicationPages: vi.fn(() => null),
}));

import { applyFillPlan, getProfile } from "./client";

function profile(): ProfileSnapshot {
  return {
    profileId: "profile-responsive",
    displayName: "Responsive profile",
    facts: [],
    records: [],
    recordTombstones: [],
    createdAt: "2026-08-26T00:00:00.000Z",
    updatedAt: "2026-08-26T00:00:00.000Z",
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

describe("critical-path responsiveness", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vaultMocks.getProfile.mockReset();
    vaultMocks.getPagesForTab.mockReset();
  });

  it("returns a valid browser profile without waiting for background reconciliation", async () => {
    const localProfile = profile();
    vaultMocks.getProfile.mockResolvedValue(localProfile);
    const sendMessage = vi.fn(() => new Promise<unknown>(() => undefined));
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    await expect(getProfile()).resolves.toEqual(localProfile);
    expect(sendMessage).toHaveBeenCalledWith({ type: "GET_PROFILE" });
  });

  it("releases the fill UI when the service worker never answers", async () => {
    vi.useFakeTimers();
    vaultMocks.getProfile.mockResolvedValue(null);
    const sendMessage = vi.fn(() => new Promise<unknown>(() => undefined));
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const pending = applyFillPlan({ pageId: "page-1", instructions: [] });
    const rejection = expect(pending).rejects.toThrow(
      "Verified fill timed out after 20 seconds",
    );
    await vi.advanceTimersByTimeAsync(20_000);
    await rejection;
  });
});
