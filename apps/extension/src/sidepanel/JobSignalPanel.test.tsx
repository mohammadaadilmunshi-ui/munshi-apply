import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import { JobSignalPanel } from "./JobSignalPanel";

function jobPage(overrides: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-job-signals",
    tabId: 7,
    frameId: 0,
    documentId: "document-job-signals",
    url: "https://jobs.example.com/people-analytics?jobId=42",
    title: "People Analytics Analyst",
    pageContext:
      "Regular full-time role paying $82,000 - $96,000 with up to 10% travel.",
    observedAt: "2026-08-23T18:00:00.000Z",
    controls: [],
    questions: [],
    applicationState: "JOB_CONTEXT",
    pageFingerprint: "page-fingerprint-job-signals",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    ...overrides,
  };
}

describe("Job Signal side-panel presentation", () => {
  it("renders direction-aware, exact-evidence rows for the owner", () => {
    const html = renderToStaticMarkup(
      createElement(JobSignalPanel, {
        page: jobPage(),
        applicationId: "application-job-signals",
        nativeAvailable: false,
        preflightState: "READY",
        accountRequired: false,
        manualRequiredControls: 0,
      }),
    );

    expect(html).toContain('aria-labelledby="job-signal-heading"');
    expect(html).toContain("Helpful evidence");
    expect(html).toContain("Exact evidence:");
    expect(html).toContain("$82,000 - $96,000");
    expect(html).toContain("Unknown information stays unknown");
    expect(html).not.toMatch(/recruiter identity|toxic workplace/i);
  });

  it("labels final submission as an owner boundary, not a negative job signal", () => {
    const html = renderToStaticMarkup(
      createElement(JobSignalPanel, {
        page: jobPage({ finalSubmissionBoundary: true }),
        applicationId: "application-job-signals",
        nativeAvailable: false,
        preflightState: "READY",
        accountRequired: false,
        manualRequiredControls: 0,
      }),
    );

    expect(html).toContain("Final submission is an owner-control boundary");
    expect(html).toContain("does not count as evidence");
  });
});
