import { describe, expect, it, vi } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  planHistoryStateRescan,
  recoverHistoryStateChange,
  type HistoryStateRecoveryDependencies,
} from "./history-state-recovery";

function page(frameId: number): ApplicationPage {
  return {
    pageId: `page-${frameId}`,
    tabId: 9,
    frameId,
    documentId: `document-${frameId}`,
    url: `https://careers.example.test/frame/${frameId}`,
    title: `Frame ${frameId}`,
    pageContext: "Application",
    observedAt: "2026-08-17T21:30:00.000Z",
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: `fingerprint-${frameId}`,
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
  };
}

function dependencies(
  pages: ApplicationPage[],
): HistoryStateRecoveryDependencies & {
  clearTab: ReturnType<typeof vi.fn>;
  deleteFrame: ReturnType<typeof vi.fn>;
  scanFrame: ReturnType<typeof vi.fn>;
} {
  return {
    getPages: vi.fn().mockResolvedValue(pages),
    clearTab: vi.fn().mockResolvedValue(undefined),
    deleteFrame: vi.fn().mockResolvedValue(undefined),
    scanFrame: vi.fn().mockResolvedValue(undefined),
  };
}

describe("SPA history-state recovery", () => {
  it("rescans every previously known accessible frame after a top-frame route change", () => {
    expect(planHistoryStateRescan(0, [page(4), page(0), page(2)])).toEqual({
      clearWholeTab: true,
      frameIds: [0, 2, 4],
    });
  });

  it("rescans only the changed child frame for child-frame history changes", () => {
    expect(planHistoryStateRescan(4, [page(0), page(2), page(4)])).toEqual({
      clearWholeTab: false,
      frameIds: [4],
    });
  });

  it("always includes the top frame even before any snapshot was stored", () => {
    expect(planHistoryStateRescan(0, [])).toEqual({
      clearWholeTab: true,
      frameIds: [0],
    });
  });

  it("refuses invalid frame identifiers", () => {
    expect(planHistoryStateRescan(-1, [page(0)])).toEqual({
      clearWholeTab: false,
      frameIds: [],
    });
  });

  it("clears stale tab state before rescanning known frames after a top-frame SPA route", async () => {
    const runtime = dependencies([page(0), page(2), page(4)]);

    await recoverHistoryStateChange(9, 0, runtime);

    expect(runtime.clearTab).toHaveBeenCalledWith(9);
    expect(runtime.deleteFrame).not.toHaveBeenCalled();
    expect(runtime.scanFrame.mock.calls).toEqual([
      [9, 0],
      [9, 2],
      [9, 4],
    ]);
  });

  it("invalidates and rescans only a child frame after child-frame history changes", async () => {
    const runtime = dependencies([page(0), page(4)]);

    await recoverHistoryStateChange(9, 4, runtime);

    expect(runtime.clearTab).not.toHaveBeenCalled();
    expect(runtime.deleteFrame).toHaveBeenCalledWith(9, 4);
    expect(runtime.scanFrame).toHaveBeenCalledWith(9, 4);
  });

  it("ignores an inaccessible secondary frame but never hides failure of the changed frame", async () => {
    const runtime = dependencies([page(0), page(2)]);
    runtime.scanFrame.mockImplementation(
      async (_tabId: number, frameId: number) => {
        if (frameId === 2) throw new Error("frame disappeared");
      },
    );

    await expect(
      recoverHistoryStateChange(9, 0, runtime),
    ).resolves.toBeUndefined();

    const childRuntime = dependencies([page(0), page(2)]);
    childRuntime.scanFrame.mockRejectedValue(
      new Error("changed frame disappeared"),
    );
    await expect(recoverHistoryStateChange(9, 2, childRuntime)).rejects.toThrow(
      "changed frame disappeared",
    );
  });
});
