import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import { applicationPageEligibility } from "./application-detection";

function avaturePage(url: string): ApplicationPage {
  return {
    pageId: "page-avature",
    tabId: 1,
    frameId: 0,
    documentId: "doc-avature",
    url,
    title: "Workforce Intelligence Insights Partner (HR Insights)",
    observedAt: "2026-08-18T22:55:00.000-04:00",
    controls: [
      {
        controlId: "ctl-work-auth",
        frameId: 0,
        kind: "RADIO",
        tagName: "input",
        name: "workAuthorization",
        label: "Are you legally authorized to work for ANY employers, full time, in the country in which this position is located?",
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: ["Yes", "No"],
        multiple: false,
        autocomplete: "",
        invalid: false,
        validationMessage: "",
      },
    ],
    questions: [
      {
        questionId: "q-work-auth",
        controlId: "ctl-work-auth",
        rawText: "Are you legally authorized to work for ANY employers, full time, in the country in which this position is located?",
        semanticType: "WORK_AUTHORIZATION_CURRENT",
        confidence: 0.98,
        sensitive: true,
        requiresReview: false,
      },
    ],
    applicationState: "QUESTIONS",
    pageFingerprint: "fp-avature",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
  };
}

describe("Avature and strong application-form detection", () => {
  it("tracks the Bloomberg Avature ApplicationForm route even without a visible navigation control", () => {
    const result = applicationPageEligibility(
      avaturePage(
        "https://bloomberg.avature.net/careers/ApplicationForm?jobId=20572&source=linkedin",
      ),
    );

    expect(result.eligible).toBe(true);
    expect(result.reasons).toContain(
      "explicit careers application-form route with interactive fields",
    );
    expect(result.reasons).toContain("known ATS with application-specific questions");
  });

  it("does not treat unrelated paths beginning with ApplicationForm as an application route", () => {
    const page = avaturePage("https://docs.example.test/careers/ApplicationFormat");
    page.questions = [];
    page.controls = [];

    expect(applicationPageEligibility(page)).toEqual({ eligible: false, reasons: [] });
  });
});
