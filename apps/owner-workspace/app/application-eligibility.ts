import type { ApplicationReview, ApplicationSnapshot } from "./vault-client";

type RichApplicationSnapshot = ApplicationSnapshot & {
  controls?: Array<{
    kind?: string;
    label?: string;
    name?: string;
    ariaLabel?: string;
    placeholder?: string;
  }>;
  applicationState?: string;
  navigationCandidates?: Array<{
    action?: string;
    label?: string;
  }>;
  finalSubmissionBoundary?: boolean;
  atsFamily?: string;
};

const explicitApplicationIntent =
  /(?:^|[\s/_?=&.-])(apply|application|candidate|requisition)(?:$|[\s/_?=&.-])/i;
const resumeLabel = /\b(resume|résumé|cv)\b/i;
const applicationNavigation = /\b(apply|application)\b/i;
const applicationSpecificSemantics = new Set([
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

function origin(value: string): string | null {
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function hasExplicitIntent(page: RichApplicationSnapshot): boolean {
  try {
    const url = new URL(page.url);
    return explicitApplicationIntent.test(
      `${url.pathname} ${url.search} ${page.title}`,
    );
  } catch {
    return false;
  }
}

/**
 * Compatibility filter for encrypted APPLICATION.V1 records. This mirrors the
 * desktop producer gate so legacy broad-observation snapshots remain encrypted
 * in history but no longer appear as job applications on the owner workspace.
 */
export function isEligibleApplicationSnapshot(
  snapshot: ApplicationSnapshot,
  workspaceOrigin?: string | null,
): boolean {
  const page = snapshot as RichApplicationSnapshot;
  const pageOrigin = origin(page.url);
  if (!pageOrigin) return false;
  if (workspaceOrigin && pageOrigin === origin(workspaceOrigin)) return false;

  const knownAts = Boolean(page.atsFamily && page.atsFamily !== "GENERIC");
  const explicitIntent = hasExplicitIntent(page);
  const meaningfulQuestions = page.questions.filter(
    (question) => question.semanticType !== "UNKNOWN",
  ).length;
  const specificQuestions = page.questions.filter((question) =>
    applicationSpecificSemantics.has(question.semanticType),
  ).length;
  const resumeControl = Boolean(
    page.controls?.some(
      (control) =>
        control.kind === "FILE" &&
        resumeLabel.test(
          `${control.label ?? ""} ${control.name ?? ""} ${control.ariaLabel ?? ""} ${control.placeholder ?? ""}`,
        ),
    ),
  );
  const applicationNav = Boolean(
    page.navigationCandidates?.some(
      (candidate) =>
        candidate.action !== "BACK" &&
        applicationNavigation.test(candidate.label ?? ""),
    ),
  );

  return Boolean(
    page.finalSubmissionBoundary ||
      (resumeControl && (knownAts || explicitIntent)) ||
      (applicationNav &&
        (knownAts || explicitIntent || specificQuestions > 0) &&
        meaningfulQuestions > 0) ||
      (page.applicationState !== "AUTH" &&
        explicitIntent &&
        meaningfulQuestions >= 2) ||
      (knownAts && specificQuestions > 0) ||
      (knownAts &&
        page.applicationState === "CONFIRMATION" &&
        explicitIntent),
  );
}

export function pendingReviewCount(
  application: ApplicationSnapshot,
  review?: ApplicationReview | null,
): number {
  const approvedQuestionIds = new Set(
    (review?.answers ?? [])
      .filter((answer) => answer.approved)
      .map((answer) => answer.questionId),
  );
  return application.questions.filter(
    (question) =>
      question.requiresReview && !approvedQuestionIds.has(question.questionId),
  ).length;
}
