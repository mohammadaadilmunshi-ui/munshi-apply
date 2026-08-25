import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  RECENT_JOB_CONTEXT_GRACE_MS,
  beginRecentContextRetention,
  classifyJobContext,
  recentContextIsVisible,
  remainingRecentContextMs,
} from "./reliability-core";

function page(overrides: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-1",
    tabId: 4,
    frameId: 0,
    documentId: "doc-1",
    url: "https://careers.example.com/jobs/123",
    title: "People Analytics Specialist",
    pageContext:
      "Job description. Responsibilities include workforce reporting and analytics. Requirements include Excel and HRIS experience. ".repeat(
        8,
      ),
    observedAt: "2026-08-25T08:00:00.000Z",
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: "fingerprint",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "UNKNOWN",
    ...overrides,
  };
}

describe("recent job context", () => {
  it("recognizes a real job listing but rejects an unrelated page", () => {
    expect(classifyJobContext(page())).toBe("LISTING");
    expect(
      classifyJobContext(
        page({
          url: "https://example.com/news",
          title: "Weather report",
          pageContext: "General news and weather coverage. ".repeat(30),
        }),
      ),
    ).toBeNull();
  });

  it("retains context for three minutes and then expires it", () => {
    const started = 10_000;
    const retained = beginRecentContextRetention(
      {
        page: page(),
        kind: "LISTING",
        capturedAt: started,
        retainedUntil: null,
      },
      started,
    );
    expect(remainingRecentContextMs(retained, started)).toBe(
      RECENT_JOB_CONTEXT_GRACE_MS,
    );
    expect(
      recentContextIsVisible(
        retained,
        started + RECENT_JOB_CONTEXT_GRACE_MS - 1,
      ),
    ).toBe(true);
    expect(
      recentContextIsVisible(retained, started + RECENT_JOB_CONTEXT_GRACE_MS),
    ).toBe(false);
  });
});
