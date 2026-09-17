import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import { mergeApplicationPages } from "./page-merge";

function page(
  frameId: number,
  input: Partial<ApplicationPage> = {},
): ApplicationPage {
  return {
    pageId: `page-${frameId}`,
    tabId: 7,
    frameId,
    documentId: `document-${frameId}`,
    url:
      frameId === 0
        ? "https://careers.example.test/apply"
        : `https://frame.example.test/${frameId}`,
    title: frameId === 0 ? "Application" : `Frame ${frameId}`,
    pageContext: frameId === 0 ? "Candidate application" : "",
    observedAt: `2026-08-17T20:00:0${frameId}.000Z`,
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: `fingerprint-${frameId}`,
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
    ...input,
  };
}

describe("multi-frame application page aggregation", () => {
  it("returns null when no accessible frame snapshots exist", () => {
    expect(mergeApplicationPages([])).toBeNull();
  });

  it("preserves the top frame identity while aggregating child-frame execution state", () => {
    const top = page(0, {
      controls: [
        {
          controlId: "first-name",
          frameId: 0,
          kind: "TEXT",
          tagName: "input",
          name: "firstName",
          label: "First name",
          placeholder: "",
          ariaLabel: "",
          required: true,
          disabled: false,
          visible: true,
          options: [],
          multiple: false,
          autocomplete: "given-name",
          invalid: false,
          validationMessage: "",
        },
      ],
      questions: [
        {
          questionId: "q-first-name",
          controlId: "first-name",
          rawText: "First name",
          semanticType: "FIRST_NAME",
          confidence: 0.99,
          sensitive: false,
          requiresReview: false,
        },
      ],
    });
    const child = page(4, {
      pageContext: "Verification and navigation controls",
      controls: [
        {
          controlId: "continue",
          frameId: 4,
          kind: "BUTTON",
          tagName: "button",
          name: "",
          label: "Continue",
          placeholder: "",
          ariaLabel: "",
          required: false,
          disabled: false,
          visible: true,
          options: [],
          multiple: false,
          autocomplete: "",
          invalid: false,
          validationMessage: "",
        },
      ],
      securityCheckpoint: "CAPTCHA",
      validationErrorCount: 2,
      navigationCandidates: [
        {
          controlId: "continue",
          frameId: 4,
          action: "NEXT",
          label: "Continue",
          disabled: false,
        },
      ],
      finalSubmissionBoundary: true,
      atsFamily: "WORKDAY",
    });

    const merged = mergeApplicationPages([child, top]);

    expect(merged).not.toBeNull();
    expect(merged?.pageId).toBe("page-0");
    expect(merged?.documentId).toBe("document-0");
    expect(merged?.controls.map((control) => control.frameId)).toEqual([4, 0]);
    expect(merged?.navigationCandidates).toEqual(child.navigationCandidates);
    expect(merged?.securityCheckpoint).toBe("CAPTCHA");
    expect(merged?.validationErrorCount).toBe(2);
    expect(merged?.finalSubmissionBoundary).toBe(true);
    expect(merged?.atsFamily).toBe("WORKDAY");
    expect(merged?.pageContext).toContain("Candidate application");
    expect(merged?.pageContext).toContain(
      "Verification and navigation controls",
    );
    expect(merged?.observedAt).toBe(child.observedAt);
  });

  it("uses the strongest security checkpoint across accessible frames", () => {
    const merged = mergeApplicationPages([
      page(0, { securityCheckpoint: "AUTHENTICATION" }),
      page(2, { securityCheckpoint: "OTP" }),
      page(3, { securityCheckpoint: "IDENTITY_VERIFICATION" }),
    ]);
    expect(merged?.securityCheckpoint).toBe("IDENTITY_VERIFICATION");
  });

  it("changes the merged fingerprint when only a child frame changes", () => {
    const top = page(0);
    const child = page(2, { pageFingerprint: "child-before" });
    const before = mergeApplicationPages([top, child]);
    const after = mergeApplicationPages([
      top,
      { ...child, pageFingerprint: "child-after" },
    ]);

    expect(before?.pageId).toBe(after?.pageId);
    expect(before?.pageFingerprint).not.toBe(after?.pageFingerprint);
  });

  it("keeps questions only when their own frame still contains the target control", () => {
    const orphaned = page(3, {
      questions: [
        {
          questionId: "q-missing",
          controlId: "missing-control",
          rawText: "Missing",
          semanticType: "UNKNOWN",
          confidence: 0.2,
          sensitive: false,
          requiresReview: true,
        },
      ],
    });
    const valid = page(2, {
      controls: [
        {
          controlId: "email",
          frameId: 2,
          kind: "EMAIL",
          tagName: "input",
          name: "email",
          label: "Email",
          placeholder: "",
          ariaLabel: "",
          required: true,
          disabled: false,
          visible: true,
          options: [],
          multiple: false,
          autocomplete: "email",
          invalid: false,
          validationMessage: "",
        },
      ],
      questions: [
        {
          questionId: "q-email",
          controlId: "email",
          rawText: "Email",
          semanticType: "EMAIL",
          confidence: 0.99,
          sensitive: false,
          requiresReview: false,
        },
      ],
    });

    expect(
      mergeApplicationPages([page(0), orphaned, valid])?.questions.map(
        (question) => question.questionId,
      ),
    ).toEqual(["q-email"]);
  });

  it("withholds automatic questions when the same control ID exists in multiple frames", () => {
    const duplicateControl = (frameId: number) => ({
      controlId: "ctl-same-signature",
      frameId,
      kind: "TEXT" as const,
      tagName: "input",
      name: "email",
      label: "Email",
      placeholder: "",
      ariaLabel: "",
      required: true,
      disabled: false,
      visible: true,
      options: [],
      multiple: false,
      autocomplete: "email",
      invalid: false,
      validationMessage: "",
    });
    const duplicateQuestion = (suffix: string) => ({
      questionId: `q-email-${suffix}`,
      controlId: "ctl-same-signature",
      rawText: "Email",
      semanticType: "EMAIL" as const,
      confidence: 0.99,
      sensitive: false,
      requiresReview: false,
    });
    const top = page(0, {
      controls: [duplicateControl(0)],
      questions: [duplicateQuestion("top")],
    });
    const child = page(3, {
      controls: [duplicateControl(3)],
      questions: [duplicateQuestion("child")],
      navigationCandidates: [
        {
          controlId: "continue-child",
          frameId: 3,
          action: "NEXT",
          label: "Continue",
          disabled: false,
        },
      ],
    });

    const merged = mergeApplicationPages([top, child]);

    expect(merged?.controls).toHaveLength(2);
    expect(merged?.questions).toEqual([]);
    expect(merged?.navigationCandidates).toEqual(child.navigationCandidates);
  });
});
