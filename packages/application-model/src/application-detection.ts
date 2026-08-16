import type { ApplicationPage, SemanticType } from "@munshi-apply/contracts";

const explicitApplicationIntent =
  /(?:^|[\s/_?=&#.-])(apply|application|requisition)(?:$|[\s/_?=&#.-])/i;
const candidateRegistrationIntent =
  /(?:^|[\s/_?=&#.-])(register|registration|candidate)(?:$|[\s/_?=&#.-])/i;
const careerOrJobContext =
  /(?:^|[\s/_.-])(career|careers|job|jobs|recruiting|recruitment)(?:$|[\s/_.-])/i;
const strongJobRegistrationRoute =
  /\/(?:jobs?|careers?)\/register(?:\/|$)/i;
const resumeLabel = /\b(resume|résumé|cv)\b/i;
const applicationNavigation = /\b(apply|application)\b/i;

const applicationSpecificSemantics = new Set<SemanticType>([
  "EDUCATION",
  "SCHOOL_NAME",
  "DEGREE",
  "FIELD_OF_STUDY",
  "GRADUATION_DATE",
  "GPA",
  "EMPLOYMENT",
  "EMPLOYER_NAME",
  "JOB_TITLE",
  "EMPLOYMENT_DATES",
  "EMPLOYMENT_RESPONSIBILITIES",
  "WORK_AUTHORIZATION_CURRENT",
  "SPONSORSHIP_CURRENT",
  "SPONSORSHIP_FUTURE",
  "IMMIGRATION_ASSISTANCE",
  "SALARY_EXPECTATION",
  "START_DATE",
  "NOTICE_PERIOD",
  "RELOCATION",
  "TRAVEL",
  "SKILLS",
  "CERTIFICATIONS",
  "LICENSES",
  "SECURITY_CLEARANCE",
  "VETERAN_STATUS",
  "PROTECTED_VETERAN_STATUS",
  "DISABILITY_STATUS",
  "GENDER",
  "RACE_ETHNICITY",
  "EEO_SELF_ID",
  "REFERRAL",
  "PREVIOUS_EMPLOYEE",
  "PREVIOUS_APPLICATION",
  "CONFLICT_OF_INTEREST",
  "NON_COMPETE",
  "BACKGROUND_CHECK",
  "DRUG_SCREENING",
  "WHY_COMPANY",
  "WHY_ROLE",
  "RELEVANT_EXPERIENCE",
  "CAREER_GOALS",
  "BEHAVIORAL_EXAMPLE",
]);

const candidateIdentitySemantics = new Set<SemanticType>([
  "FIRST_NAME",
  "MIDDLE_NAME",
  "LAST_NAME",
  "PREFERRED_NAME",
  "EMAIL",
  "PHONE",
  "STREET_ADDRESS",
  "ADDRESS_LINE_2",
  "CITY",
  "STATE_PROVINCE",
  "POSTAL_CODE",
  "COUNTRY",
]);

export type ApplicationEligibility = {
  eligible: boolean;
  reasons: string[];
};

function hasExplicitIntent(page: ApplicationPage): boolean {
  try {
    const url = new URL(page.url);
    return explicitApplicationIntent.test(
      `${url.pathname} ${url.search} ${url.hash} ${page.title}`,
    );
  } catch {
    return false;
  }
}

function hasCandidateRegistrationIntent(page: ApplicationPage): boolean {
  try {
    const url = new URL(page.url);
    const context = `${url.hostname} ${url.pathname} ${url.search} ${url.hash} ${page.title}`;
    return (
      candidateRegistrationIntent.test(context) &&
      careerOrJobContext.test(context)
    );
  } catch {
    return false;
  }
}

function hasStrongJobRegistrationRoute(page: ApplicationPage): boolean {
  try {
    const url = new URL(page.url);
    return (
      strongJobRegistrationRoute.test(url.pathname) &&
      careerOrJobContext.test(`${url.hostname} ${url.pathname} ${page.title}`)
    );
  } catch {
    return false;
  }
}

function meaningfulQuestionCount(page: ApplicationPage): number {
  const questions = Array.isArray(page.questions) ? page.questions : [];
  return questions.filter((question) => question.semanticType !== "UNKNOWN")
    .length;
}

function applicationSpecificQuestionCount(page: ApplicationPage): number {
  const questions = Array.isArray(page.questions) ? page.questions : [];
  return questions.filter((question) =>
    applicationSpecificSemantics.has(question.semanticType),
  ).length;
}

function candidateIdentityQuestionCount(page: ApplicationPage): number {
  const questions = Array.isArray(page.questions) ? page.questions : [];
  return questions.filter((question) =>
    candidateIdentitySemantics.has(question.semanticType),
  ).length;
}

function interactiveFieldCount(page: ApplicationPage): number {
  const controls = Array.isArray(page.controls) ? page.controls : [];
  return controls.filter(
    (control) =>
      control.kind !== "BUTTON" && control.visible && !control.disabled,
  ).length;
}

function hasResumeControl(page: ApplicationPage): boolean {
  const controls = Array.isArray(page.controls) ? page.controls : [];
  return controls.some(
    (control) =>
      control.kind === "FILE" &&
      resumeLabel.test(
        `${control.label} ${control.name} ${control.ariaLabel} ${control.placeholder}`,
      ),
  );
}

function hasApplicationNavigation(page: ApplicationPage): boolean {
  const navigationCandidates = Array.isArray(page.navigationCandidates)
    ? page.navigationCandidates
    : [];
  return navigationCandidates.some(
    (candidate) =>
      candidate.action !== "BACK" &&
      applicationNavigation.test(candidate.label),
  );
}

function hasApplicationProgression(page: ApplicationPage): boolean {
  const navigationCandidates = Array.isArray(page.navigationCandidates)
    ? page.navigationCandidates
    : [];
  return navigationCandidates.some(
    (candidate) =>
      !candidate.disabled &&
      ["NEXT", "REVIEW", "FINAL_SUBMIT"].includes(candidate.action),
  );
}

/**
 * Decide whether an observed browser page has enough deterministic evidence to
 * enter the application ledger. The scanner observes broadly, while this gate
 * rejects ordinary browsing. Multi-step careers registration flows are allowed
 * to remain tracked between steps even when the current step has no visible
 * Next button or résumé control.
 */
export function applicationPageEligibility(
  page: ApplicationPage,
): ApplicationEligibility {
  const reasons: string[] = [];
  const knownAts = Boolean(page.atsFamily && page.atsFamily !== "GENERIC");
  const explicitIntent = hasExplicitIntent(page);
  const candidateRegistration = hasCandidateRegistrationIntent(page);
  const strongJobRegistration = hasStrongJobRegistrationRoute(page);
  const meaningfulQuestions = meaningfulQuestionCount(page);
  const specificQuestions = applicationSpecificQuestionCount(page);
  const candidateIdentityQuestions = candidateIdentityQuestionCount(page);
  const interactiveFields = interactiveFieldCount(page);
  const resumeControl = hasResumeControl(page);
  const applicationNav = hasApplicationNavigation(page);
  const applicationProgression = hasApplicationProgression(page);

  if (page.finalSubmissionBoundary) {
    reasons.push("verified final-application boundary");
  }
  if (resumeControl && (knownAts || explicitIntent || candidateRegistration)) {
    reasons.push("résumé control inside application context");
  }
  if (
    page.applicationState !== "AUTH" &&
    resumeControl &&
    candidateIdentityQuestions >= 2 &&
    applicationProgression
  ) {
    reasons.push(
      "embedded candidate form with résumé control and application progression",
    );
  }
  if (
    applicationNav &&
    (knownAts ||
      explicitIntent ||
      candidateRegistration ||
      specificQuestions > 0) &&
    meaningfulQuestions > 0
  ) {
    reasons.push("application-specific navigation with form questions");
  }
  if (
    page.applicationState !== "AUTH" &&
    explicitIntent &&
    meaningfulQuestions >= 2
  ) {
    reasons.push(
      "explicit application context with multiple classified questions",
    );
  }
  if (strongJobRegistration && interactiveFields >= 2) {
    reasons.push("explicit careers job-registration route with candidate fields");
  }
  if (
    page.applicationState !== "AUTH" &&
    candidateRegistration &&
    interactiveFields >= 2 &&
    (specificQuestions >= 1 || candidateIdentityQuestions >= 2)
  ) {
    reasons.push("careers/job registration flow with candidate form evidence");
  }
  if (
    page.applicationState !== "AUTH" &&
    candidateRegistration &&
    applicationProgression &&
    interactiveFields >= 2
  ) {
    reasons.push(
      "careers/job registration flow with progressive candidate fields",
    );
  }
  if (
    page.applicationState !== "AUTH" &&
    applicationProgression &&
    candidateIdentityQuestions >= 2 &&
    (explicitIntent || candidateRegistration || specificQuestions > 0)
  ) {
    reasons.push(
      "candidate identity form with verified application progression",
    );
  }
  if (knownAts && specificQuestions > 0) {
    reasons.push("known ATS with application-specific questions");
  }
  if (knownAts && page.applicationState === "CONFIRMATION" && explicitIntent) {
    reasons.push("known ATS application confirmation");
  }

  return { eligible: reasons.length > 0, reasons };
}

export function isEligibleApplicationPage(page: ApplicationPage): boolean {
  return applicationPageEligibility(page).eligible;
}
