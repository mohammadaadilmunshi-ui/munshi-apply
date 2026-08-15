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
});
