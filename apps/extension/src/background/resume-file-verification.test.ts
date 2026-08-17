import { describe, expect, it } from "vitest";
import type { ApplicationPage, Control } from "@munshi-apply/contracts";
import {
  isResumeFileControl,
  resumeVerificationBlocksNavigation,
  verifySelectedResumeFile,
} from "./resume-file-verification";

const digest = "a".repeat(64);

function fileControl(input: Partial<Control> = {}): Control {
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
    fileSelected: false,
    fileFingerprintState: "NONE",
    fileSha256: null,
    ...input,
  };
}

function page(controls: Control[]): ApplicationPage {
  return {
    pageId: "page-resume",
    tabId: 1,
    frameId: 0,
    documentId: "document-resume",
    url: "https://careers.example.test/apply",
    title: "Application",
    pageContext: "Résumé upload",
    observedAt: "2026-08-17T22:00:00.000Z",
    controls,
    questions: [],
    applicationState: "DOCUMENTS",
    pageFingerprint: "fingerprint-resume",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
  };
}

describe("résumé file verification", () => {
  it("recognizes résumé/CV fields but not other attachments", () => {
    expect(isResumeFileControl(fileControl())).toBe(true);
    expect(
      isResumeFileControl(
        fileControl({ name: "cv", label: "Curriculum Vitae / CV" }),
      ),
    ).toBe(true);
    expect(
      isResumeFileControl(
        fileControl({ name: "coverLetter", label: "Upload cover letter" }),
      ),
    ).toBe(false);
    expect(
      isResumeFileControl(
        fileControl({ name: "portfolio", label: "Portfolio attachment" }),
      ),
    ).toBe(false);
  });

  it("blocks a required résumé field until a file is selected", () => {
    const result = verifySelectedResumeFile({
      page: page([fileControl()]),
      selectedResumeSha256: digest,
    });
    expect(result.state).toBe("REQUIRED_MISSING");
    expect(resumeVerificationBlocksNavigation(result)).toBe(true);
  });

  it("requires every mandatory résumé field when an ATS exposes more than one", () => {
    const result = verifySelectedResumeFile({
      page: page([
        fileControl({
          controlId: "resume-primary",
          fileSelected: true,
          fileFingerprintState: "READY",
          fileSha256: digest,
        }),
        fileControl({
          controlId: "resume-secondary",
          name: "cv",
          label: "CV",
        }),
      ]),
      selectedResumeSha256: digest,
    });
    expect(result.state).toBe("REQUIRED_MISSING");
    expect(result.controlIds).toEqual(["resume-secondary"]);
    expect(resumeVerificationBlocksNavigation(result)).toBe(true);
  });

  it("allows an optional résumé field to remain empty", () => {
    const result = verifySelectedResumeFile({
      page: page([fileControl({ required: false })]),
      selectedResumeSha256: digest,
    });
    expect(result.state).toBe("OPTIONAL_EMPTY");
    expect(resumeVerificationBlocksNavigation(result)).toBe(false);
  });

  it("waits for the selected file fingerprint before navigation", () => {
    const result = verifySelectedResumeFile({
      page: page([
        fileControl({
          fileSelected: true,
          fileFingerprintState: "PENDING",
          fileSha256: null,
        }),
      ]),
      selectedResumeSha256: digest,
    });
    expect(result.state).toBe("PENDING");
    expect(resumeVerificationBlocksNavigation(result)).toBe(true);
  });

  it("blocks a selected résumé whose digest does not match the application résumé", () => {
    const result = verifySelectedResumeFile({
      page: page([
        fileControl({
          fileSelected: true,
          fileFingerprintState: "READY",
          fileSha256: "b".repeat(64),
        }),
      ]),
      selectedResumeSha256: digest,
    });
    expect(result.state).toBe("MISMATCH");
    expect(resumeVerificationBlocksNavigation(result)).toBe(true);
  });

  it("accepts the exact selected résumé digest", () => {
    const result = verifySelectedResumeFile({
      page: page([
        fileControl({
          fileSelected: true,
          fileFingerprintState: "READY",
          fileSha256: digest,
        }),
      ]),
      selectedResumeSha256: digest,
    });
    expect(result.state).toBe("MATCH");
    expect(resumeVerificationBlocksNavigation(result)).toBe(false);
  });

  it("does not apply the résumé digest to cover letters or generic attachments", () => {
    const result = verifySelectedResumeFile({
      page: page([
        fileControl({
          name: "coverLetter",
          label: "Cover letter",
          fileSelected: true,
          fileFingerprintState: "READY",
          fileSha256: "b".repeat(64),
        }),
      ]),
      selectedResumeSha256: digest,
    });
    expect(result.state).toBe("NOT_APPLICABLE");
    expect(resumeVerificationBlocksNavigation(result)).toBe(false);
  });
});
