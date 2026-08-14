import type {
  ApplicationState,
  FillInstruction,
  FillResult,
} from "@munshi-apply/contracts";
import { canTransition } from "./index";
import type { PreflightGateSummary } from "./policies";

export type SecurityCheckpointKind =
  | "CAPTCHA"
  | "MFA"
  | "OTP"
  | "IDENTITY_VERIFICATION"
  | "AUTHENTICATION";

export type AutoPilotObservation = {
  applicationId: string;
  state: ApplicationState;
  pageId: string;
  pageFingerprint: string;
  visibleControlIds: readonly string[];
  validationErrorCount: number;
  securityCheckpoint: SecurityCheckpointKind | null;
  canNavigateNext: boolean;
  isFinalSubmissionStep: boolean;
};

export type AutoPilotCheckpoint = {
  checkpointId: string;
  applicationId: string;
  sequence: number;
  state: ApplicationState;
  pageId: string;
  pageFingerprint: string;
  completedControlIds: readonly string[];
  pendingControlIds: readonly string[];
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
  createdAt: string;
};

export type AutoPilotAction =
  | { type: "FILL"; instruction: FillInstruction }
  | { type: "NAVIGATE_NEXT" }
  | { type: "PAUSE_REVIEW"; reason: string }
  | { type: "PAUSE_SECURITY"; checkpoint: SecurityCheckpointKind }
  | { type: "PAUSE_FINAL_APPROVAL" }
  | { type: "WAIT"; reason: string };

export type AutoPilotPlan = {
  action: AutoPilotAction;
  checkpointRequired: boolean;
  reason: string;
};

export type ActionVerification = {
  success: boolean;
  reason: string;
};

function nextApprovedInstruction(
  instructions: readonly FillInstruction[],
  completedControlIds: ReadonlySet<string>,
  visibleControlIds: ReadonlySet<string>,
): FillInstruction | null {
  return (
    instructions.find(
      (instruction) =>
        instruction.approved &&
        !completedControlIds.has(instruction.controlId) &&
        visibleControlIds.has(instruction.controlId),
    ) ?? null
  );
}

export function planAutoPilotStep(input: {
  observation: AutoPilotObservation;
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
  completedControlIds?: readonly string[];
}): AutoPilotPlan {
  const { observation, preflight } = input;
  if (observation.securityCheckpoint) {
    return {
      action: {
        type: "PAUSE_SECURITY",
        checkpoint: observation.securityCheckpoint,
      },
      checkpointRequired: true,
      reason: "Browser security checkpoint requires deliberate owner action",
    };
  }

  if (observation.isFinalSubmissionStep || observation.state === "SUBMISSION") {
    return {
      action: { type: "PAUSE_FINAL_APPROVAL" },
      checkpointRequired: true,
      reason: "Final submission is always a deliberate owner checkpoint",
    };
  }

  if (!preflight.canAct) {
    return {
      action: {
        type: "PAUSE_REVIEW",
        reason: `Pre-flight gate is ${preflight.state}`,
      },
      checkpointRequired: true,
      reason: "Unresolved or review-required items must be resolved before action",
    };
  }

  if (observation.validationErrorCount > 0) {
    return {
      action: {
        type: "PAUSE_REVIEW",
        reason: "Current page contains validation errors",
      },
      checkpointRequired: true,
      reason: "Validation failures must be resolved before navigation",
    };
  }

  const instruction = nextApprovedInstruction(
    input.fillInstructions,
    new Set(input.completedControlIds ?? []),
    new Set(observation.visibleControlIds),
  );
  if (instruction) {
    return {
      action: { type: "FILL", instruction },
      checkpointRequired: false,
      reason: "Apply one approved visible instruction and verify before continuing",
    };
  }

  if (observation.canNavigateNext) {
    return {
      action: { type: "NAVIGATE_NEXT" },
      checkpointRequired: true,
      reason: "Current page is resolved; checkpoint before navigation",
    };
  }

  return {
    action: { type: "WAIT", reason: "No verified action is currently available" },
    checkpointRequired: false,
    reason: "Observe again before taking another action",
  };
}

export function createAutoPilotCheckpoint(input: {
  checkpointId: string;
  observation: AutoPilotObservation;
  sequence: number;
  completedControlIds: readonly string[];
  pendingControlIds: readonly string[];
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
  createdAt: string;
}): AutoPilotCheckpoint {
  if (!Number.isSafeInteger(input.sequence) || input.sequence < 0) {
    throw new Error("Checkpoint sequence must be a non-negative integer");
  }
  return {
    checkpointId: input.checkpointId,
    applicationId: input.observation.applicationId,
    sequence: input.sequence,
    state: input.observation.state,
    pageId: input.observation.pageId,
    pageFingerprint: input.observation.pageFingerprint,
    completedControlIds: [...new Set(input.completedControlIds)],
    pendingControlIds: [...new Set(input.pendingControlIds)],
    selectedResumeId: input.selectedResumeId,
    selectedResumeSha256: input.selectedResumeSha256,
    createdAt: input.createdAt,
  };
}

export function canResumeFromCheckpoint(
  checkpoint: AutoPilotCheckpoint,
  observation: AutoPilotObservation,
): { resumable: boolean; reason: string } {
  if (checkpoint.applicationId !== observation.applicationId) {
    return { resumable: false, reason: "Checkpoint belongs to another application" };
  }
  if (checkpoint.state === observation.state) {
    return { resumable: true, reason: "Observation matches checkpoint state" };
  }
  if (canTransition(checkpoint.state, observation.state)) {
    return {
      resumable: true,
      reason: "Observation is a valid forward transition from the checkpoint",
    };
  }
  return {
    resumable: false,
    reason: "Observed application state is incompatible with the checkpoint",
  };
}

export function verifyFillAction(
  controlId: string,
  results: readonly FillResult[],
): ActionVerification {
  const result = results.find((candidate) => candidate.controlId === controlId);
  if (!result) {
    return { success: false, reason: "No fill verification result was returned" };
  }
  return {
    success: result.status === "FILLED",
    reason: result.reason,
  };
}

export function verifyNavigationAction(
  before: AutoPilotObservation,
  after: AutoPilotObservation,
): ActionVerification {
  if (before.applicationId !== after.applicationId) {
    return { success: false, reason: "Navigation left the active application" };
  }
  if (
    before.pageFingerprint === after.pageFingerprint &&
    before.pageId === after.pageId &&
    before.state === after.state
  ) {
    return {
      success: false,
      reason: "Navigation produced no verified page or state change",
    };
  }
  if (before.state !== after.state && !canTransition(before.state, after.state)) {
    return {
      success: false,
      reason: "Navigation produced an invalid application-state transition",
    };
  }
  return { success: true, reason: "Navigation produced a verified application change" };
}
