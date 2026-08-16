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
  requiredReviewCount: number;
  optionalReviewCount: number;
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

export function remainingApprovedFillCount(
  plan: AutoPilotLaunchPlan,
  completedControlIds: readonly string[] = [],
): number {
  const completed = new Set(completedControlIds);
  return plan.fillInstructions.filter(
    (instruction) =>
      instruction.approved && !completed.has(instruction.controlId),
  ).length;
}

export function canAutoPilotMakeProgress(
  plan: AutoPilotLaunchPlan,
  completedControlIds: readonly string[] = [],
): boolean {
  if (plan.preflight.canAct) return true;
  return (
    plan.preflight.blockedCount === 0 &&
    remainingApprovedFillCount(plan, completedControlIds) > 0
  );
}

export function buildAutoPilotLaunchPlan(
  page: ApplicationPage,
  answers: Record<string, AutoPilotAnswer>,
  options: { expectedResumeSha256?: string | null } = {},
): AutoPilotLaunchPlan {
  const controls = new Map(
    page.controls.map((control) => [control.controlId, control]),
  );
  const instructions: FillInstruction[] = [];
  const manual = new Map<string, Control>();
  let requiredReviewCount = 0;
  let optionalReviewCount = 0;
  let unresolvedCount = 0;
  let optionalUnansweredCount = 0;

  for (const question of page.questions) {
    const control = controls.get(question.controlId);
    if (!control || control.disabled) continue;
    if (control.kind === "FILE") {
      const resumeLike = /\b(resume|résumé|cv)\b/i.test(
        `${control.label} ${control.name} ${control.ariaLabel}`,
      );
      if (!control.fileSelected) {
        manual.set(control.controlId, control);
      } else if (resumeLike && options.expectedResumeSha256) {
        if (control.fileFingerprintState !== "READY") {
          manual.set(control.controlId, {
            ...control,
            invalid: true,
            validationMessage:
              "Selected résumé is still being fingerprinted locally; wait for verification before continuing.",
          });
        } else if (control.fileSha256 !== options.expectedResumeSha256) {
          manual.set(control.controlId, {
            ...control,
            invalid: true,
            validationMessage:
              "Selected résumé does not match the résumé version bound to this application.",
          });
        }
      }
      continue;
    }
    if (!control.visible) continue;
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
      if (control.required) requiredReviewCount += 1;
      else optionalReviewCount += 1;
      continue;
    }
    instructions.push({
      controlId: question.controlId,
      frameId: control.frameId,
      value: answer.value,
      sensitive: question.sensitive,
      approved: true,
      sourceDraftId: answer.sourceDraftId ?? undefined,
    });
  }

  for (const control of page.controls) {
    if (
      !control.disabled &&
      control.required &&
      (control.kind === "FILE" || control.visible) &&
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
      : requiredReviewCount > 0 || unresolvedCount > 0 || manualCount > 0
        ? "REVIEW"
        : "READY";
  const preflight: PreflightGateSummary = {
    state,
    readyCount: instructions.length,
    reviewCount: requiredReviewCount + optionalReviewCount + manualCount,
    unresolvedCount,
    blockedCount,
    canAct: state === "READY",
  };
  return {
    preflight,
    fillInstructions: instructions,
    manualControls: [...manual.values()],
    optionalUnansweredCount,
    requiredReviewCount,
    optionalReviewCount,
  };
}
