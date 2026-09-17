import { describe, expect, it } from "vitest";
import type { ApplicationPage, Control } from "@munshi-apply/contracts";
import { evaluateForwardNavigationSafety } from "./forward-navigation-safety";

const resumeDigest = "a".repeat(64);

function page(input: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-navigation-safety",
    tabId: 1,
    frameId: 0,
    documentId: "document-navigation-safety",
    url: "https://careers.example.test/apply",
    title: "Application",
    pageContext: "Application",
    observedAt: "2026-08-17T22:10:00.000Z",
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: "fingerprint-navigation-safety",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
    ...input,
  };
}

function resumeControl(input: Partial<Control> = {}): Control {
  return {
    controlId: "resume-file",
    frameId: 0,
    kind: "FILE",
    tagName: "input",
    name: "resume",
    label: "Upload résumé",
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
    fileSelected: true,
    fileFingerprintState: "READY",
    fileSha256: resumeDigest,
    ...input,
  };
}

describe("forward navigation safety", () => {
  it("requires owner review whenever the employer page is already in REVIEW state", () => {
    expect(
      evaluateForwardNavigationSafety({
        page: page({ applicationState: "REVIEW" }),
        selectedResumeSha256: null,
      }),
    ).toEqual({
      safe: false,
      reason:
        "This employer page is in application review state. Review the application before continuing.",
    });
  });

  it("blocks navigation while the résumé digest is still pending", () => {
    const result = evaluateForwardNavigationSafety({
      page: page({
        controls: [
          resumeControl({
            fileFingerprintState: "PENDING",
            fileSha256: null,
          }),
        ],
      }),
      selectedResumeSha256: resumeDigest,
    });
    expect(result.safe).toBe(false);
    if (!result.safe) expect(result.reason).toContain("has not finished");
  });

  it("blocks navigation when the employer résumé field contains another file", () => {
    const result = evaluateForwardNavigationSafety({
      page: page({
        controls: [resumeControl({ fileSha256: "b".repeat(64) })],
      }),
      selectedResumeSha256: resumeDigest,
    });
    expect(result.safe).toBe(false);
    if (!result.safe) expect(result.reason).toContain("does not match");
  });

  it("allows ordinary forward navigation after the exact résumé digest is verified", () => {
    expect(
      evaluateForwardNavigationSafety({
        page: page({ controls: [resumeControl()] }),
        selectedResumeSha256: resumeDigest,
      }),
    ).toEqual({ safe: true });
  });

  it("does not block pages that have no résumé field", () => {
    expect(
      evaluateForwardNavigationSafety({
        page: page(),
        selectedResumeSha256: resumeDigest,
      }),
    ).toEqual({ safe: true });
  });
});
