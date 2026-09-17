import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  hasJobContextAffinity,
  mergeJobContext,
  shouldRememberJobContext,
  type StoredJobContext,
} from "./job-context";

function page(input: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-test",
    tabId: 1,
    frameId: 0,
    documentId: "doc-test",
    url: "https://careers.example.test/jobs/recruiter-123",
    title: "Recruiter",
    pageContext: "",
    observedAt: "2026-08-16T00:00:00.000Z",
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: "fp-test",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
    ...input,
  };
}

describe("job listing context carryover", () => {
  it("remembers a non-application careers page with real job-description signals", () => {
    const context = (
      "About the role. Responsibilities include building candidate relationships and coordinating recruiting processes. " +
      "Requirements include communication, organization, stakeholder partnership, and analytical skills. "
    ).repeat(8);
    expect(shouldRememberJobContext(page({ pageContext: context }))).toBe(true);
  });

  it("does not overwrite listing context with an application form", () => {
    const application = page({
      url: "https://careers.example.test/jobs/Register?id=123",
      pageContext: "Personal information First name Last name Email".repeat(20),
      controls: [
        {
          controlId: "first",
          frameId: 0,
          kind: "TEXT",
          tagName: "input",
          name: "first",
          label: "First name",
          placeholder: "",
          ariaLabel: "",
          required: true,
          disabled: false,
          visible: true,
          options: [],
          multiple: false,
          autocomplete: "",
          invalid: false,
          validationMessage: "",
        },
        {
          controlId: "last",
          frameId: 0,
          kind: "TEXT",
          tagName: "input",
          name: "last",
          label: "Last name",
          placeholder: "",
          ariaLabel: "",
          required: true,
          disabled: false,
          visible: true,
          options: [],
          multiple: false,
          autocomplete: "",
          invalid: false,
          validationMessage: "",
        },
      ],
      questions: [
        {
          questionId: "q-first",
          controlId: "first",
          rawText: "First name",
          semanticType: "FIRST_NAME",
          confidence: 0.94,
          sensitive: false,
          requiresReview: false,
        },
        {
          questionId: "q-last",
          controlId: "last",
          rawText: "Last name",
          semanticType: "LAST_NAME",
          confidence: 0.94,
          sensitive: false,
          requiresReview: false,
        },
      ],
      navigationCandidates: [
        {
          controlId: "next",
          frameId: 0,
          action: "NEXT",
          label: "Next",
          disabled: false,
        },
      ],
    });
    expect(shouldRememberJobContext(application)).toBe(false);
  });

  it("merges a recent listing into the later same-origin application context", () => {
    const stored: StoredJobContext = {
      url: "https://careers.example.test/jobs/recruiter-123",
      title: "Recruiter",
      pageContext:
        "Responsibilities include candidate sourcing and stakeholder partnership.",
      capturedAt: "2026-08-16T00:00:00.000Z",
    };
    const application = page({
      url: "https://careers.example.test/jobs/Register?id=123",
      pageContext: "Work history Company Title Start date",
    });
    const merged = mergeJobContext(
      application,
      stored,
      Date.parse("2026-08-16T00:30:00.000Z"),
    );
    expect(merged.pageContext).toContain(
      "Job listing context captured before the application",
    );
    expect(merged.pageContext).toContain(
      "candidate sourcing and stakeholder partnership",
    );
    expect(merged.pageContext).toContain(
      "Work history Company Title Start date",
    );
  });

  it("allows a cross-origin ATS handoff when the employer identity is present", () => {
    const stored: StoredJobContext = {
      url: "https://careers.acme.test/jobs/people-analytics-associate",
      title: "People Analytics Associate at Acme",
      pageContext:
        "Responsibilities include workforce reporting and people analytics partnership.",
      capturedAt: "2026-08-16T00:00:00.000Z",
    };
    const application = page({
      url: "https://acme.wd5.myworkdayjobs.com/en-US/jobs/apply/people-analytics-associate",
      title: "People Analytics Associate application",
      pageContext: "Personal information Work history",
    });

    expect(hasJobContextAffinity(application, stored)).toBe(true);
    expect(
      mergeJobContext(
        application,
        stored,
        Date.parse("2026-08-16T00:10:00.000Z"),
      ).pageContext,
    ).toContain("workforce reporting and people analytics partnership");
  });

  it("refuses stale context from a different employer reused in the same tab", () => {
    const stored: StoredJobContext = {
      url: "https://careers.acme.test/jobs/people-analytics-associate",
      title: "People Analytics Associate at Acme",
      pageContext:
        "Responsibilities include workforce reporting and people analytics partnership.",
      capturedAt: "2026-08-16T00:00:00.000Z",
    };
    const application = page({
      url: "https://differentco.wd5.myworkdayjobs.com/en-US/jobs/apply/coordinator",
      title: "Candidate application",
      pageContext: "Personal information Work history Contact information",
    });

    expect(hasJobContextAffinity(application, stored)).toBe(false);
    expect(
      mergeJobContext(
        application,
        stored,
        Date.parse("2026-08-16T00:10:00.000Z"),
      ).pageContext,
    ).toBe("Personal information Work history Contact information");
  });

  it("ignores stale listing context", () => {
    const stored: StoredJobContext = {
      url: "https://careers.example.test/jobs/recruiter-123",
      title: "Recruiter",
      pageContext: "Responsibilities and requirements.",
      capturedAt: "2026-08-16T00:00:00.000Z",
    };
    const application = page({
      url: "https://careers.example.test/jobs/Register?id=123",
      pageContext: "Application",
    });
    expect(
      mergeJobContext(
        application,
        stored,
        Date.parse("2026-08-16T03:00:00.000Z"),
      ).pageContext,
    ).toBe("Application");
  });
});
