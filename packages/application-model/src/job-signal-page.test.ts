import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import { buildPageJobSignalSource } from "./job-signal-page";

function page(overrides: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-1",
    tabId: 1,
    frameId: 0,
    documentId: "document-1",
    url: "https://jobs.example.com/job/people-analyst?source=board#apply",
    title: "People Analyst | Example",
    pageContext: "High-volume role with up to 25% travel.",
    observedAt: "2026-08-17T20:40:00.000Z",
    controls: [],
    questions: [],
    applicationState: "JOB_CONTEXT",
    pageFingerprint: "page-fingerprint-1",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    ...overrides,
  };
}

describe("Job Signal page adapter", () => {
  it("uses captured text only on an explicit job-context page", () => {
    const source = buildPageJobSignalSource(page());
    expect(source.input.description).toBe(
      "High-volume role with up to 25% travel.",
    );
    expect(source.input.role).toBeUndefined();
    expect(source.input.company).toBeUndefined();
    expect(source.input.compensation).toBeUndefined();
  });

  it("does not reinterpret application questions as job-posting evidence", () => {
    const source = buildPageJobSignalSource(
      page({
        applicationState: "QUESTIONS",
        title: "Application Questions",
        pageContext:
          "Will you require sponsorship? Are you willing to work weekends?",
      }),
    );
    expect(source.input.description).toBeNull();
    expect(source.input.role).toBeUndefined();
    expect(source.input.company).toBeUndefined();
  });

  it("includes observed workflow friction without treating it as job text", () => {
    const source = buildPageJobSignalSource(
      page({ applicationState: "QUESTIONS", validationErrorCount: 2 }),
      { accountRequired: true, manualRequiredControls: 3 },
    );
    expect(source.input.description).toBeNull();
    expect(source.input.applicationFriction).toEqual({
      accountRequired: true,
      manualRequiredControls: 3,
      validationErrors: 2,
    });
  });

  it("normalizes invalid manual-control counts to zero", () => {
    const source = buildPageJobSignalSource(page(), {
      manualRequiredControls: -4,
    });
    expect(source.input.applicationFriction?.manualRequiredControls).toBe(0);
  });

  it("keeps a stable fingerprint across timestamps and query/hash tracking changes", () => {
    const first = buildPageJobSignalSource(page()).sourceFingerprint;
    const second = buildPageJobSignalSource(
      page({
        observedAt: "2026-08-17T20:41:00.000Z",
        url: "https://jobs.example.com/job/people-analyst?source=other#details",
      }),
    ).sourceFingerprint;
    expect(second).toBe(first);
  });

  it("changes the fingerprint when analyzed job evidence changes", () => {
    const first = buildPageJobSignalSource(page()).sourceFingerprint;
    const changedContext = buildPageJobSignalSource(
      page({ pageContext: "Role requires up to 60% travel." }),
    ).sourceFingerprint;
    const changedStructure = buildPageJobSignalSource(
      page({ pageFingerprint: "page-fingerprint-2" }),
    ).sourceFingerprint;
    expect(changedContext).not.toBe(first);
    expect(changedStructure).not.toBe(first);
  });
});
