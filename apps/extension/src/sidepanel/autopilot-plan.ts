import type {
  ApplicationPage,
  Control,
  FillInstruction,
} from "@munshi-apply/contracts";
import {
  accountPreflightItem,
  buildAccountOrchestrationPlan,
  evaluateCurrentPageKnockouts,
  type AccountOrchestrationPlan,
  type AccountRecord,
  type EmployerPreflightFinding,
  type PreflightGateSummary,
} from "@munshi-apply/application-model";

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
  accountPlan: AccountOrchestrationPlan;
  employerKnockoutFindings: EmployerPreflightFinding[];
};

export type AutoPilotLaunchPlanOptions = {
  expectedResumeSha256?: string | null;
  knownAccounts?: readonly AccountRecord[];
  preferredEmail?: string | null;
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
  options: AutoPilotLaunchPlanOptions = {},
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

  const accountPlan = buildAccountOrchestrationPlan({
    page,
    knownAccounts: options.knownAccounts,
    preferredEmail: options.preferredEmail,
  });
  const accountItem = accountPreflightItem(accountPlan);
  const accountBlocked = accountItem.state === "BLOCKED";
  const accountReviewCount = accountItem.state === "REVIEW" ? 1 : 0;

  const employerKnockoutFindings = evaluateCurrentPageKnockouts(page, answers);
  const employerBlockedCount = employerKnockoutFindings.filter(
    (finding) => finding.state === "BLOCKED",
  ).length;
  const employerReviewCount = employerKnockoutFindings.filter(
    (finding) => finding.state === "REVIEW",
  ).length;
  const employerUnresolvedCount = employerKnockoutFindings.filter(
    (finding) => finding.state === "UNRESOLVED",
  ).length;
  const unsafeEmployerSemanticTypes = new Set(
    employerKnockoutFindings
      .filter((finding) => finding.state !== "READY")
      .map((finding) => finding.requirement.semanticType),
  );
  const unsafeEmployerControlIds = new Set(
    page.questions
      .filter((question) =>
        unsafeEmployerSemanticTypes.has(question.semanticType),
      )
      .map((question) => question.controlId),
  );
  const guardedInstructions = instructions.filter(
    (instruction) => !unsafeEmployerControlIds.has(instruction.controlId),
  );

  const hardSecurityCheckpoint =
    page.securityCheckpoint !== null &&
    page.securityCheckpoint !== "AUTHENTICATION";
  const securityOrAccountBoundary = hardSecurityCheckpoint || accountBlocked;
  const blockedCount =
    (securityOrAccountBoundary ? 1 : 0) +
    (page.finalSubmissionBoundary ? 1 : 0) +
    employerBlockedCount;
  const totalUnresolvedCount = unresolvedCount + employerUnresolvedCount;
  const manualCount = manual.size;
  const blockingReviewCount =
    requiredReviewCount + accountReviewCount + employerReviewCount;

  let state: PreflightGateSummary["state"] = "READY";
  if (blockedCount > 0) {
    state = "BLOCKED";
  } else if (
    blockingReviewCount > 0 ||
    totalUnresolvedCount > 0 ||
    manualCount > 0
  ) {
    state = "REVIEW";
  }

  const preflight: PreflightGateSummary = {
    state,
    readyCount: guardedInstructions.length,
    reviewCount:
      requiredReviewCount +
      optionalReviewCount +
      manualCount +
      accountReviewCount +
      employerReviewCount,
    unresolvedCount: totalUnresolvedCount,
    blockedCount,
    canAct: state === "READY",
  };
  return {
    preflight,
    fillInstructions: guardedInstructions,
    manualControls: [...manual.values()],
    optionalUnansweredCount,
    requiredReviewCount,
    optionalReviewCount,
    accountPlan,
    employerKnockoutFindings,
  };
}
