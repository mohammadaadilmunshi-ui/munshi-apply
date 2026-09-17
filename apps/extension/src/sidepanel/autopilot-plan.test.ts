import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  buildAutoPilotLaunchPlan,
  canAutoPilotMakeProgress,
  remainingApprovedFillCount,
} from "./autopilot-plan";

function page(): ApplicationPage {
  return {
    pageId: "page-1",
    tabId: 1,
    frameId: 0,
    documentId: "doc-1",
    url: "https://example.com/apply",
    title: "Apply",
    observedAt: "2026-08-14T23:00:00.000Z",
    controls: [
      {
        controlId: "name",
        frameId: 0,
        kind: "TEXT",
        tagName: "input",
        name: "name",
        label: "Name",
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: [],
        multiple: false,
        autocomplete: "name",
        invalid: false,
        validationMessage: "",
        fileSelected: false,
      },
      {
        controlId: "resume",
        frameId: 0,
        kind: "FILE",
        tagName: "input",
        name: "resume",
        label: "Resume",
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
      },
    ],
    questions: [
      {
        questionId: "q-name",
        controlId: "name",
        rawText: "Name",
        semanticType: "PERSONAL",
        confidence: 1,
        sensitive: false,
        requiresReview: false,
      },
      {
        questionId: "q-resume",
        controlId: "resume",
        rawText: "Resume",
        semanticType: "UNKNOWN",
        confidence: 0,
        sensitive: false,
        requiresReview: true,
      },
    ],
    applicationState: "RESUME",
    pageFingerprint: "fingerprint",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
  };
}

describe("buildAutoPilotLaunchPlan", () => {
  it("preserves safe progress while an unselected required file remains manual", () => {
    const result = buildAutoPilotLaunchPlan(page(), {
      "q-name": { value: "Aadil", approved: true, sensitive: false },
    });
    expect(result.preflight.state).toBe("REVIEW");
    expect(result.manualControls.map((item) => item.controlId)).toEqual([
      "resume",
    ]);
    expect(result.fillInstructions).toHaveLength(1);
    expect(remainingApprovedFillCount(result)).toBe(1);
    expect(canAutoPilotMakeProgress(result)).toBe(true);
    expect(canAutoPilotMakeProgress(result, ["name"])).toBe(false);
  });

  it("allows the step after the owner selected the file", () => {
    const current = page();
    current.controls[1] = { ...current.controls[1]!, fileSelected: true };
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": { value: "Aadil", approved: true, sensitive: false },
    });
    expect(result.preflight.state).toBe("READY");
    expect(result.manualControls).toHaveLength(0);
    expect(canAutoPilotMakeProgress(result, ["name"])).toBe(true);
  });

  it("does not expose safe-progress mode across a hard safety boundary", () => {
    const current = page();
    current.finalSubmissionBoundary = true;
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": { value: "Aadil", approved: true, sensitive: false },
    });
    expect(result.preflight.state).toBe("BLOCKED");
    expect(result.preflight.blockedCount).toBe(1);
    expect(canAutoPilotMakeProgress(result)).toBe(false);
  });

  it("does not block page progress for an optional answer that has not been approved", () => {
    const current = page();
    current.controls = [{ ...current.controls[0]!, required: false }];
    current.questions = [current.questions[0]!];
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": { value: "Optional note", approved: false, sensitive: false },
    });
    expect(result.preflight.state).toBe("READY");
    expect(result.preflight.canAct).toBe(true);
    expect(result.requiredReviewCount).toBe(0);
    expect(result.optionalReviewCount).toBe(1);
  });

  it("still blocks navigation for a required answer that has not been approved", () => {
    const current = page();
    current.controls = [current.controls[0]!];
    current.questions = [current.questions[0]!];
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": { value: "Required value", approved: false, sensitive: false },
    });
    expect(result.preflight.state).toBe("REVIEW");
    expect(result.preflight.canAct).toBe(false);
    expect(result.requiredReviewCount).toBe(1);
    expect(result.optionalReviewCount).toBe(0);
  });

  it("carries an approved AI draft identity into the AutoPilot fill instruction", () => {
    const current = page();
    current.controls = [current.controls[0]!];
    current.questions = [current.questions[0]!];
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": {
        value: "Evidence-backed answer",
        approved: true,
        sensitive: false,
        sourceDraftId: "draft-1",
      },
    });
    expect(result.fillInstructions[0]?.sourceDraftId).toBe("draft-1");
  });

  it("allows safe identity preparation on recognized account creation, then stops before navigation", () => {
    const current = page();
    current.controls = [current.controls[0]!];
    current.questions = [current.questions[0]!];
    current.url = "https://example.com/candidate/register";
    current.applicationState = "ACCOUNT_CREATE";
    current.securityCheckpoint = "AUTHENTICATION";
    current.pageContext = "Create account for a new candidate";
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": { value: "Aadil", approved: true, sensitive: false },
    });
    expect(result.accountPlan.flow).toBe("AUTH_CREATE");
    expect(result.preflight.blockedCount).toBe(0);
    expect(result.preflight.reviewCount).toBe(1);
    expect(result.preflight.state).toBe("REVIEW");
    expect(result.fillInstructions.map((item) => item.controlId)).toEqual([
      "name",
    ]);
    expect(canAutoPilotMakeProgress(result)).toBe(true);
    expect(canAutoPilotMakeProgress(result, ["name"])).toBe(false);
  });

  it("recognizes a known portal account and prevents duplicate creation", () => {
    const current = page();
    current.controls = [current.controls[0]!];
    current.questions = [current.questions[0]!];
    current.url = "https://example.com/candidate/register";
    current.applicationState = "ACCOUNT_CREATE";
    current.securityCheckpoint = "AUTHENTICATION";
    current.pageContext = "Create account for a new candidate";
    const result = buildAutoPilotLaunchPlan(
      current,
      {
        "q-name": { value: "Aadil", approved: true, sensitive: false },
      },
      {
        knownAccounts: [
          {
            accountId: "account-1",
            employer: "Example",
            domain: "example.com",
            scopeKey: "example.com",
            portalUrl: "https://example.com/candidate/login",
            email: "aadil@example.com",
            exists: true,
            createdAt: "2026-08-01T12:00:00.000Z",
            lastUsed: "2026-08-17T12:00:00.000Z",
            applicationIds: [],
          },
        ],
      },
    );
    expect(result.accountPlan.state).toBe("DUPLICATE_RISK");
    expect(result.accountPlan.knownAccount?.email).toBe("aadil@example.com");
    expect(result.preflight.state).toBe("BLOCKED");
  });

  it("hard-blocks an approved answer that violates an explicit employer knockout", () => {
    const current = page();
    current.controls = [
      {
        ...current.controls[0]!,
        controlId: "sponsor",
        name: "sponsor",
        label: "Sponsorship",
      },
    ];
    current.questions = [
      {
        questionId: "q-sponsor",
        controlId: "sponsor",
        rawText: "Will you now or in the future require sponsorship?",
        semanticType: "SPONSORSHIP_FUTURE",
        confidence: 1,
        sensitive: true,
        requiresReview: true,
      },
    ];
    current.pageContext = "This employer does not offer visa sponsorship.";
    const result = buildAutoPilotLaunchPlan(current, {
      "q-sponsor": { value: "Yes", approved: true, sensitive: true },
    });
    expect(result.employerKnockoutFindings).toHaveLength(1);
    expect(result.employerKnockoutFindings[0]?.state).toBe("BLOCKED");
    expect(result.fillInstructions).toHaveLength(0);
    expect(result.preflight.state).toBe("BLOCKED");
    expect(canAutoPilotMakeProgress(result)).toBe(false);
  });

  it("withholds an unresolved knockout answer while allowing unrelated safe fields first", () => {
    const current = page();
    current.controls = [
      current.controls[0]!,
      {
        ...current.controls[0]!,
        controlId: "sponsor",
        name: "sponsor",
        label: "Sponsorship",
      },
    ];
    current.questions = [
      current.questions[0]!,
      {
        questionId: "q-sponsor",
        controlId: "sponsor",
        rawText: "Will you now or in the future require sponsorship?",
        semanticType: "SPONSORSHIP_FUTURE",
        confidence: 1,
        sensitive: true,
        requiresReview: true,
      },
    ];
    current.pageContext = "This employer does not offer visa sponsorship.";
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": { value: "Aadil", approved: true, sensitive: false },
      "q-sponsor": { value: "Maybe", approved: true, sensitive: true },
    });
    expect(result.employerKnockoutFindings[0]?.state).toBe("UNRESOLVED");
    expect(result.preflight.state).toBe("REVIEW");
    expect(result.preflight.unresolvedCount).toBe(1);
    expect(result.fillInstructions.map((item) => item.controlId)).toEqual([
      "name",
    ]);
    expect(canAutoPilotMakeProgress(result)).toBe(true);
    expect(canAutoPilotMakeProgress(result, ["name"])).toBe(false);
  });
});
