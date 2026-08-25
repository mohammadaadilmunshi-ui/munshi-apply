import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  RECENT_APPLICATION_CONTEXT_TTL_MS,
  createRecentApplicationContext,
  isRecentApplicationContextFresh,
  parseRecentApplicationContext,
  recentContextBelongsToTab,
} from "./recent-application-context";

function page(tabId = 17): ApplicationPage {
  return {
    pageId: "page-job",
    tabId,
    frameId: 0,
    documentId: "doc-job",
    url: "https://jobs.example.test/apply/123",
    title: "Example role",
    pageContext: "Example role application",
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
  };
}

describe("recent application context", () => {
  it("retains a job application for a bounded three-minute grace period", () => {
    const now = 1_000_000;
    const context = createRecentApplicationContext(page(), now);
    expect(context.expiresAt).toBe(now + RECENT_APPLICATION_CONTEXT_TTL_MS);
    expect(isRecentApplicationContextFresh(context, now + 1_000)).toBe(true);
    expect(
      isRecentApplicationContextFresh(
        context,
        now + RECENT_APPLICATION_CONTEXT_TTL_MS,
      ),
    ).toBe(false);
  });

  it("rejects stale or malformed persisted context", () => {
    const now = 10_000;
    expect(
      parseRecentApplicationContext(
        { page: page(), capturedAt: 1, expiresAt: now - 1 },
        now,
      ),
    ).toBeNull();
    expect(parseRecentApplicationContext({ nope: true }, now)).toBeNull();
  });

  it("tracks the original application tab so unrelated tabs cannot act on it", () => {
    const context = createRecentApplicationContext(page(41), 100);
    expect(recentContextBelongsToTab(context, 41)).toBe(true);
    expect(recentContextBelongsToTab(context, 42)).toBe(false);
  });
});
