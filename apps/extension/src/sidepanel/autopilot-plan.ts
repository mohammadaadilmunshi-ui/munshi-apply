import type {
  ApplicationPage,
  Control,
  FillInstruction,
} from "@munshi-apply/contracts";
import type { PreflightGateSummary } from "@munshi-apply/application-model";

export type AutoPilotAnswer = {
  value: string;
  approved: boolean;
  sensitive: boolean;
  sourceDraftId?: string | null;
};

export type AutoPilotLaunchPlan = {
  preflight: PreflightGateSummary;
  fillInstructions: FillInstruction[];
  manualControls: Control[];
  optionalUnansweredCount: number;
};

const fillableKinds = new Set([
  "TEXT",
  "EMAIL",
  "TEL",
  "NUMBER",
  "DATE",
  "TEXTAREA",
  "SELECT",
  "CHECKBOX",
  "RADIO",
  "COMBOBOX",
]);

export function buildAutoPilotLaunchPlan(
  page: ApplicationPage,
  answers: Record<string, AutoPilotAnswer>,
): AutoPilotLaunchPlan {
  const controls = new Map(page.controls.map((control) => [control.controlId, control]));
  const instructions: FillInstruction[] = [];
  const manual = new Map<string, Control>();
  let reviewCount = 0;
  let unresolvedCount = 0;
  let optionalUnansweredCount = 0;

  for (const question of page.questions) {
    const control = controls.get(question.controlId);
    if (!control || control.disabled || !control.visible) continue;
    if (control.kind === "FILE") {
      if (!control.fileSelected) manual.set(control.controlId, control);
      continue;
    }
    if (!fillableKinds.has(control.kind)) {
      if (control.required) manual.set(control.controlId, control);
      continue;
    }
    const answer = answers[question.questionId];
    const value = answer?.value.trim() ?? "";
    if (!value) {
      if (control.required) unresolvedCount += 1;
      else optionalUnansweredCount += 1;
      continue;
    }
    if (!answer?.approved) {
      reviewCount += 1;
      continue;
    }
    instructions.push({
      controlId: question.controlId,
      frameId: control.frameId,
      value: answer.value,
      sensitive: question.sensitive,
      approved: true,
    });
  }

  for (const control of page.controls) {
    if (
      control.visible &&
      !control.disabled &&
      control.required &&
      (control.kind === "FILE" || !fillableKinds.has(control.kind)) &&
      !(control.kind === "FILE" && control.fileSelected)
    ) {
      manual.set(control.controlId, control);
    }
  }

  const blockedCount =
    (page.securityCheckpoint ? 1 : 0) + (page.finalSubmissionBoundary ? 1 : 0);
  const manualCount = manual.size;
  const state =
    blockedCount > 0
      ? "BLOCKED"
      : reviewCount > 0 || unresolvedCount > 0 || manualCount > 0
        ? "REVIEW"
        : "READY";
  const preflight: PreflightGateSummary = {
    state,
    readyCount: instructions.length,
    reviewCount: reviewCount + manualCount,
    unresolvedCount,
    blockedCount,
    canAct: state === "READY",
  };
  return {
    preflight,
    fillInstructions: instructions,
    manualControls: [...manual.values()],
    optionalUnansweredCount,
  };
}
