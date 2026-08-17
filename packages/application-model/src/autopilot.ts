import {
  applicationStates,
  type ApplicationState,
  type FillInstruction,
  type FillResult,
  type SecurityCheckpointKind,
} from "@munshi-apply/contracts";
import type { PreflightGateSummary } from "./policies";
import { canTransition } from "./transitions";

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
  unresolvedRequiredControlIds?: readonly string[];
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

const applicationStateSet = new Set<string>(applicationStates);

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function nullableString(value: unknown, name: string): string | null {
  if (value === null) return null;
  return requiredString(value, name);
}

function uniqueStringArray(value: unknown, name: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`${name} must be an array`);
  }
  const items = value.map((item) => requiredString(item, name));
  if (new Set(items).size !== items.length) {
    throw new Error(`${name} must not contain duplicates`);
  }
  return items;
}

function assertIsoTimestamp(value: string, name: string): void {
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value) || Number.isNaN(Date.parse(value))) {
    throw new Error(`${name} must be an ISO timestamp`);
  }
}

export function isHardSecurityCheckpoint(
  checkpoint: SecurityCheckpointKind | null,
): boolean {
  return checkpoint !== null && checkpoint !== "AUTHENTICATION";
}

export function parseAutoPilotCheckpoint(value: unknown): AutoPilotCheckpoint {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Checkpoint payload must be an object");
  }

  const candidate = value as Record<string, unknown>;
  if (
    !Number.isSafeInteger(candidate.sequence) ||
    Number(candidate.sequence) < 0
  ) {
    throw new Error("Checkpoint sequence must be a non-negative integer");
  }
  if (
    typeof candidate.state !== "string" ||
    !applicationStateSet.has(candidate.state)
  ) {
    throw new Error("Checkpoint state is invalid");
  }

  const completedControlIds = uniqueStringArray(
    candidate.completedControlIds,
    "completedControlIds",
  );
  const pendingControlIds = uniqueStringArray(
    candidate.pendingControlIds,
    "pendingControlIds",
  );
  const completed = new Set(completedControlIds);
  if (pendingControlIds.some((controlId) => completed.has(controlId))) {
    throw new Error(
      "Completed and pending checkpoint controls must not overlap",
    );
  }

  const selectedResumeId = nullableString(
    candidate.selectedResumeId,
    "selectedResumeId",
  );
  const selectedResumeSha256 = nullableString(
    candidate.selectedResumeSha256,
    "selectedResumeSha256",
  );
  if ((selectedResumeId === null) !== (selectedResumeSha256 === null)) {
    throw new Error(
      "Résumé checkpoint identity and digest must be stored together",
    );
  }
  if (
    selectedResumeSha256 !== null &&
    !/^[a-f0-9]{64}$/.test(selectedResumeSha256)
  ) {
    throw new Error("selectedResumeSha256 must be a lowercase SHA-256 digest");
  }

  const createdAt = requiredString(candidate.createdAt, "createdAt");
  assertIsoTimestamp(createdAt, "createdAt");

  return {
    checkpointId: requiredString(candidate.checkpointId, "checkpointId"),
    applicationId: requiredString(candidate.applicationId, "applicationId"),
    sequence: Number(candidate.sequence),
    state: candidate.state as ApplicationState,
    pageId: requiredString(candidate.pageId, "pageId"),
    pageFingerprint: requiredString(
      candidate.pageFingerprint,
      "pageFingerprint",
    ),
    completedControlIds,
    pendingControlIds,
    selectedResumeId,
    selectedResumeSha256,
    createdAt,
  };
}

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
  if (
    observation.securityCheckpoint &&
    isHardSecurityCheckpoint(observation.securityCheckpoint)
  ) {
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

  if (preflight.blockedCount > 0) {
    return {
      action: {
        type: "PAUSE_REVIEW",
        reason: "Pre-flight contains a hard safety block",
      },
      checkpointRequired: true,
      reason: "Hard-blocked facts or policy findings require owner resolution",
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
      reason:
        "Apply one approved visible instruction and verify before continuing",
    };
  }

  if (observation.securityCheckpoint === "AUTHENTICATION") {
    return {
      action: {
        type: "PAUSE_REVIEW",
        reason: "Authentication credential entry requires owner action",
      },
      checkpointRequired: true,
      reason:
        "Approved non-secret authentication preparation is complete; credentials and navigation remain owner controlled",
    };
  }

  if (!preflight.canAct) {
    return {
      action: {
        type: "PAUSE_REVIEW",
        reason: `Pre-flight gate is ${preflight.state}`,
      },
      checkpointRequired: true,
      reason:
        "Approved safe fills are complete; unresolved or review-required items must be resolved before navigation",
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

  const unresolvedRequired = observation.unresolvedRequiredControlIds ?? [];
  if (unresolvedRequired.length > 0) {
    return {
      action: {
        type: "PAUSE_REVIEW",
        reason:
          "A required control appeared after the current fill plan was prepared",
      },
      checkpointRequired: true,
      reason:
        "Re-scan and rebuild the fill plan before continuing through a dependent form",
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
    action: {
      type: "WAIT",
      reason: "No verified action is currently available",
    },
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
  return parseAutoPilotCheckpoint({
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
  });
}

export function canResumeFromCheckpoint(
  checkpoint: AutoPilotCheckpoint,
  observation: AutoPilotObservation,
): { resumable: boolean; reason: string } {
  if (checkpoint.applicationId !== observation.applicationId) {
    return {
      resumable: false,
      reason: "Checkpoint belongs to another application",
    };
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
    return {
      success: false,
      reason: "No fill verification result was returned",
    };
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
  if (
    before.state !== after.state &&
    !canTransition(before.state, after.state)
  ) {
    return {
      success: false,
      reason: "Navigation produced an invalid application-state transition",
    };
  }
  return {
    success: true,
    reason: "Navigation produced a verified application change",
  };
}
