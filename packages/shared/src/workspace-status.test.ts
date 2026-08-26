import { describe, expect, it } from "vitest";
import {
  conflictPresentation,
  loadingWorkspaceOverview,
  manualSyncPresentation,
  renderWorkspaceCount,
  workspaceOverviewFromAuthority,
} from "./workspace-status";

describe("hosted workspace status contract", () => {
  it("never uses a dash for device-count loading or error states", () => {
    expect(renderWorkspaceCount({ state: "loading" })).toBe("Loading…");
    expect(renderWorkspaceCount({ state: "ready", value: 0 })).toBe("0");
    expect(renderWorkspaceCount({ state: "ready", value: 1 })).toBe("1");
    expect(
      renderWorkspaceCount({ state: "error", message: "network failed" }),
    ).toBe("Unable to load");
  });

  it("derives every overview metric from one authority snapshot", () => {
    const overview = workspaceOverviewFromAuthority({
      activeDeviceCount: 1,
      confirmedFactCount: 7,
      encryptedResumeCount: 2,
      answersToReviewCount: 3,
      syncEventCount: 53,
      historicalConflictCount: 13,
      unresolvedConflictCount: 0,
    });

    expect(renderWorkspaceCount(overview.activeDevices)).toBe("1");
    expect(renderWorkspaceCount(overview.syncEvents)).toBe("53");
    expect(renderWorkspaceCount(overview.historicalConflicts)).toBe("13");
    expect(renderWorkspaceCount(overview.unresolvedConflicts)).toBe("0");
  });

  it("keeps historical conflict events separate from unresolved conflicts", () => {
    expect(
      conflictPresentation(
        { state: "ready", value: 13 },
        { state: "ready", value: 0 },
      ),
    ).toEqual({
      primaryLabel: "Unresolved conflicts",
      primaryValue: "0",
      secondaryText: "13 historical conflict events",
      requiresAttention: false,
    });

    expect(
      conflictPresentation(
        { state: "ready", value: 13 },
        { state: "ready", value: 2 },
      ).requiresAttention,
    ).toBe(true);
  });

  it("shows manual sync only as a fallback or explicit idle action", () => {
    expect(
      manualSyncPresentation({
        state: "synced",
        acknowledgedAt: "2026-08-14T17:00:00.000Z",
      }).visible,
    ).toBe(false);
    expect(manualSyncPresentation({ state: "saving" }).visible).toBe(false);
    expect(manualSyncPresentation({ state: "idle" })).toEqual({
      visible: true,
      label: "Sync now",
      disabled: false,
    });
    expect(
      manualSyncPresentation({ state: "error", message: "offline" }),
    ).toEqual({ visible: true, label: "Retry sync", disabled: false });
  });

  it("starts every metric in an explicit loading state", () => {
    const overview = loadingWorkspaceOverview();
    expect(renderWorkspaceCount(overview.activeDevices)).toBe("Loading…");
    expect(renderWorkspaceCount(overview.confirmedFacts)).toBe("Loading…");
    expect(renderWorkspaceCount(overview.encryptedResumes)).toBe("Loading…");
  });

  it("rejects impossible negative authority counters", () => {
    expect(() =>
      workspaceOverviewFromAuthority({
        activeDeviceCount: -1,
        confirmedFactCount: 0,
        encryptedResumeCount: 0,
        answersToReviewCount: 0,
        syncEventCount: 0,
        historicalConflictCount: 0,
        unresolvedConflictCount: 0,
      }),
    ).toThrow("activeDeviceCount must be a non-negative safe integer");
  });
});
