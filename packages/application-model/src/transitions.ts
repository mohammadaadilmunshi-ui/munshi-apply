import type { ApplicationState } from "@munshi-apply/contracts";

const transitions: Readonly<
  Record<ApplicationState, readonly ApplicationState[]>
> = {
  JOB_CONTEXT: ["AUTH", "PERSONAL", "RESUME", "QUESTIONS"],
  AUTH: ["ACCOUNT_CREATE", "VERIFY_ACCOUNT", "PERSONAL"],
  ACCOUNT_CREATE: ["VERIFY_ACCOUNT", "PERSONAL"],
  VERIFY_ACCOUNT: ["PERSONAL", "EDUCATION", "EXPERIENCE"],
  PERSONAL: ["EDUCATION", "EXPERIENCE", "RESUME", "QUESTIONS"],
  EDUCATION: ["EXPERIENCE", "RESUME", "QUESTIONS"],
  EXPERIENCE: ["RESUME", "QUESTIONS", "EEO"],
  RESUME: ["QUESTIONS", "EEO", "DISCLOSURES", "REVIEW"],
  QUESTIONS: ["EEO", "DISCLOSURES", "REVIEW"],
  EEO: ["DISCLOSURES", "REVIEW"],
  DISCLOSURES: ["REVIEW"],
  REVIEW: ["SUBMISSION"],
  SUBMISSION: ["CONFIRMATION"],
  CONFIRMATION: ["COMPLETE"],
  COMPLETE: [],
};

export function canTransition(
  from: ApplicationState,
  to: ApplicationState,
): boolean {
  return transitions[from].includes(to);
}

export function assertTransition(
  from: ApplicationState,
  to: ApplicationState,
): void {
  if (!canTransition(from, to)) {
    throw new Error(`Invalid application transition: ${from} -> ${to}`);
  }
}

export function allowedTransitions(
  state: ApplicationState,
): readonly ApplicationState[] {
  return transitions[state];
}
