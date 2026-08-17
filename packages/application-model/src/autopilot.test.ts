import type { FillInstruction, FillResult } from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import {
  canResumeFromCheckpoint,
  createAutoPilotCheckpoint,
  parseAutoPilotCheckpoint,
  planAutoPilotStep,
  verifyFillAction,
  verifyNavigationAction,
  type AutoPilotObservation,
} from "./autopilot";
import type { PreflightGateSummary } from "./policies";

const readyGate: PreflightGateSummary = {
  state: "READY",
  readyCount: 1,
  reviewCount: 0,
  unresolvedCount: 0,
  blockedCount: 0,
  canAct: true,
};

const reviewGate: PreflightGateSummary = {
  state: "REVIEW",
  readyCount: 1,
  reviewCount: 1,
  unresolvedCount: 1,
  blockedCount: 0,
  canAct: false,
};

const hardBlockedGate: PreflightGateSummary = {
  state: "BLOCKED",
  readyCount: 1,
  reviewCount: 0,
  unresolvedCount: 0,
  blockedCount: 1,
  canAct: false,
};

const observation: AutoPilotObservation = {
  applicationId: "app-1",
  state: "PERSONAL",
  pageId: "page-1",
  pageFingerprint: "fingerprint-1",
  visibleControlIds: ["control-1"],
  validationErrorCount: 0,
  securityCheckpoint: null,
  canNavigateNext: true,
  isFinalSubmissionStep: false,
};

const instruction: FillInstruction = {
  controlId: "control-1",
  frameId: 0,
  value: "Aadil",
  sensitive: false,
  approved: true,
};

describe("planAutoPilotStep", () => {
  it("plans only one approved visible fill before navigation", () => {
    const plan = planAutoPilotStep({
      observation,
      preflight: readyGate,
      fillInstructions: [instruction],
    });
    expect(plan.action).toEqual({ type: "FILL", instruction });
    expect(plan.checkpointRequired).toBe(false);
  });

  it("fills approved safe fields before pausing for review or unresolved items", () => {
    const plan = planAutoPilotStep({
      observation,
      preflight: reviewGate,
      fillInstructions: [instruction],
    });
    expect(plan.action).toEqual({ type: "FILL", instruction });
    expect(plan.checkpointRequired).toBe(false);
  });

  it("pauses after approved safe fills are exhausted when pre-flight is not ready", () => {
    const plan = planAutoPilotStep({
      observation,
      preflight: reviewGate,
      fillInstructions: [instruction],
      completedControlIds: ["control-1"],
    });
    expect(plan.action.type).toBe("PAUSE_REVIEW");
    expect(plan.checkpointRequired).toBe(true);
  });

  it("does not fill when pre-flight contains a hard safety block", () => {
    const plan = planAutoPilotStep({
      observation,
      preflight: hardBlockedGate,
      fillInstructions: [instruction],
    });
    expect(plan.action.type).toBe("PAUSE_REVIEW");
    expect(plan.reason).toMatch(/hard-blocked/i);
  });

  it("pauses for browser security checkpoints", () => {
    const plan = planAutoPilotStep({
      observation: { ...observation, securityCheckpoint: "MFA" },
      preflight: readyGate,
      fillInstructions: [instruction],
    });
    expect(plan.action).toEqual({ type: "PAUSE_SECURITY", checkpoint: "MFA" });
    expect(plan.checkpointRequired).toBe(true);
  });

  it("allows safe preparation on generic authentication but never navigates past it", () => {
    const authentication = {
      ...observation,
      state: "AUTH" as const,
      securityCheckpoint: "AUTHENTICATION" as const,
    };
    const first = planAutoPilotStep({
      observation: authentication,
      preflight: reviewGate,
      fillInstructions: [instruction],
    });
    expect(first.action).toEqual({ type: "FILL", instruction });
    expect(first.checkpointRequired).toBe(false);

    const afterFill = planAutoPilotStep({
      observation: authentication,
      preflight: readyGate,
      fillInstructions: [instruction],
      completedControlIds: ["control-1"],
    });
    expect(afterFill.action.type).toBe("PAUSE_REVIEW");
    expect(afterFill.reason).toMatch(
      /credentials and navigation remain owner/i,
    );
    expect(afterFill.checkpointRequired).toBe(true);
  });

  it("never plans an automatic final submission", () => {
    const plan = planAutoPilotStep({
      observation: {
        ...observation,
        state: "SUBMISSION",
        isFinalSubmissionStep: true,
      },
      preflight: readyGate,
      fillInstructions: [],
    });
    expect(plan.action.type).toBe("PAUSE_FINAL_APPROVAL");
  });

  it("checkpoints before navigating after all visible fills are verified", () => {
    const plan = planAutoPilotStep({
      observation,
      preflight: readyGate,
      fillInstructions: [instruction],
      completedControlIds: ["control-1"],
    });
    expect(plan.action.type).toBe("NAVIGATE_NEXT");
    expect(plan.checkpointRequired).toBe(true);
  });
});

describe("AutoPilot checkpoints", () => {
  it("deduplicates completed and pending controls", () => {
    const checkpoint = createAutoPilotCheckpoint({
      checkpointId: "cp-1",
      observation,
      sequence: 1,
      completedControlIds: ["a", "a", "b"],
      pendingControlIds: ["c", "c"],
      selectedResumeId: "resume-1",
      selectedResumeSha256: "a".repeat(64),
      createdAt: "2026-08-14T18:00:00.000Z",
    });
    expect(checkpoint.completedControlIds).toEqual(["a", "b"]);
    expect(checkpoint.pendingControlIds).toEqual(["c"]);
  });

  it("validates checkpoint state, timestamp, controls, and resume digest", () => {
    const valid = {
      checkpointId: "cp-1",
      applicationId: "app-1",
      sequence: 1,
      state: "PERSONAL",
      pageId: "page-1",
      pageFingerprint: "fingerprint-1",
      completedControlIds: ["a"],
      pendingControlIds: ["b"],
      selectedResumeId: "resume-1",
      selectedResumeSha256: "a".repeat(64),
      createdAt: "2026-08-14T18:00:00.000Z",
    };
    expect(parseAutoPilotCheckpoint(valid).sequence).toBe(1);
    expect(() =>
      parseAutoPilotCheckpoint({
        ...valid,
        completedControlIds: ["a", "a"],
      }),
    ).toThrow(/duplicates/);
    expect(() =>
      parseAutoPilotCheckpoint({
        ...valid,
        pendingControlIds: ["a"],
      }),
    ).toThrow(/must not overlap/);
    expect(() =>
      parseAutoPilotCheckpoint({
        ...valid,
        selectedResumeSha256: null,
      }),
    ).toThrow(/stored together/);
    expect(() =>
      parseAutoPilotCheckpoint({ ...valid, createdAt: "not-a-date" }),
    ).toThrow(/ISO timestamp/);
  });

  it("resumes only the same application at the same or valid forward state", () => {
    const checkpoint = createAutoPilotCheckpoint({
      checkpointId: "cp-1",
      observation,
      sequence: 1,
      completedControlIds: [],
      pendingControlIds: [],
      selectedResumeId: null,
      selectedResumeSha256: null,
      createdAt: "2026-08-14T18:00:00.000Z",
    });

    expect(canResumeFromCheckpoint(checkpoint, observation).resumable).toBe(
      true,
    );
    expect(
      canResumeFromCheckpoint(checkpoint, {
        ...observation,
        state: "EDUCATION",
        pageId: "page-2",
        pageFingerprint: "fingerprint-2",
      }).resumable,
    ).toBe(true);
    expect(
      canResumeFromCheckpoint(checkpoint, {
        ...observation,
        applicationId: "other-app",
      }).resumable,
    ).toBe(false);
  });
});

describe("AutoPilot action verification", () => {
  it("requires an explicit FILLED result for a fill action", () => {
    const results: FillResult[] = [
      { controlId: "control-1", status: "FILLED", reason: "verified" },
    ];
    expect(verifyFillAction("control-1", results).success).toBe(true);
    expect(verifyFillAction("missing", results).success).toBe(false);
  });

  it("rejects navigation that produces no observable change", () => {
    expect(verifyNavigationAction(observation, observation).success).toBe(
      false,
    );
  });

  it("accepts a valid forward navigation change", () => {
    const after: AutoPilotObservation = {
      ...observation,
      state: "EDUCATION",
      pageId: "page-2",
      pageFingerprint: "fingerprint-2",
    };
    expect(verifyNavigationAction(observation, after).success).toBe(true);
  });
});
