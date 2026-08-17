import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import { planHistoryStateRescan } from "./history-state-recovery";

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

describe("SPA history-state recovery planning", () => {
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
});
