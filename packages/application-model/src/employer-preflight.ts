import type {
  ApplicationPage,
  MasterProfile,
  ProfileFact,
  Question,
  SemanticType,
} from "@munshi-apply/contracts";
import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import {
  evaluateSalaryRanges,
  summarizePreflightGate,
  type PreflightGateSummary,
  type SalaryRange,
} from "./policies";
import { resolveProfileAnswer, type AnswerResolution } from "./resolver";

export type EmployerRequirementKind =
  | "WORK_AUTHORIZATION"
  | "SPONSORSHIP"
  | "CITIZENSHIP"
  | "SECURITY_CLEARANCE"
  | "DEGREE"
  | "EXPERIENCE"
  | "SALARY"
  | "START_DATE"
  | "TRAVEL"
  | "RELOCATION"
  | "WORK_MODE";

export type EmployerRequirementSource = "JOB_CONTEXT" | "APPLICATION_QUESTION";

export type EmployerRequirement = {
  requirementId: string;
  kind: EmployerRequirementKind;
  sourceKind: EmployerRequirementSource;
  sourceText: string;
  semanticType: SemanticType | null;
  expectedValues: readonly string[];
  numericValue: number | null;
  unit: string | null;
  confidence: number;
  consequential: boolean;
  knockout: boolean;
};

export type EmployerPreflightFindingState =
  "READY" | "REVIEW" | "UNRESOLVED" | "BLOCKED";

export type EmployerPreflightFinding = {
  requirement: EmployerRequirement;
  state: EmployerPreflightFindingState;
  candidateValue: string | null;
  reason: string;
};

export type EmployerPreflightReport = {
  requirements: readonly EmployerRequirement[];
  findings: readonly EmployerPreflightFinding[];
  gate: PreflightGateSummary;
};

export type EmployerAnswer = {
  value: string;
  approved: boolean;
};

type ProfileLike = MasterProfile | ProfileSnapshot;

type SourceSegment = {
  text: string;
  sourceKind: EmployerRequirementSource;
};

const authoritativeTrust = new Set([
  "VERIFIED",
  "USER_CONFIRMED",
  "DOCUMENT_CONFIRMED",
]);

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function normalize(value: string): string {
  return compact(value).toLocaleLowerCase("en-US");
}

function hash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function pageSegments(page: ApplicationPage): SourceSegment[] {
  const context = compact(page.pageContext);
  const contextSegments = context
    ? context
        .split(/(?<=[.!?])\s+|\n+/)
        .map(compact)
        .filter((text) => text.length >= 8 && text.length <= 700)
        .map((text) => ({
          text,
          sourceKind: "JOB_CONTEXT" as const,
        }))
    : [];
  const questions = page.questions
    .map((question) => compact(question.rawText))
    .filter(Boolean)
    .map((text) => ({
      text,
      sourceKind: "APPLICATION_QUESTION" as const,
    }));
  return [...contextSegments, ...questions];
}

function requirement(
  input: Omit<EmployerRequirement, "requirementId">,
): EmployerRequirement {
  const identity = [
    input.kind,
    input.sourceKind,
    normalize(input.sourceText),
    input.semanticType ?? "",
    input.expectedValues.join("|"),
    input.numericValue ?? "",
    input.unit ?? "",
  ].join("|");
  return { ...input, requirementId: `req-${hash(identity)}` };
}

function parseNumber(value: string): number | null {
  const match = value.match(/\d+(?:\.\d+)?/);
  if (!match) return null;
  const number = Number(match[0]);
  return Number.isFinite(number) ? number : null;
}

function moneyValue(raw: string, suffix: string | undefined): number | null {
  const numeric = Number(raw.replaceAll(",", ""));
  if (!Number.isFinite(numeric)) return null;
  return suffix ? numeric * 1_000 : numeric;
}

export function parseSalaryRange(text: string): SalaryRange | null {
  const normalized = normalize(text);
  if (
    !/\b(salary|pay|compensation|base|hourly|annual|yearly)\b/.test(normalized)
  ) {
    return null;
  }
  const values = Array.from(
    text.matchAll(/\$?\s*(\d{1,3}(?:,\d{3})+|\d{1,3}(?:\.\d+)?)\s*([kK])?/g),
  )
    .map((match) => moneyValue(match[1]!, match[2]))
    .filter((value): value is number => value !== null && value > 0);
  if (values.length === 0) return null;

  const period: SalaryRange["period"] =
    /\b(hour|hourly|per hour|\/hr|hr\.)\b/i.test(text) ? "HOUR" : "YEAR";
  const currency =
    /\b(?:usd|us dollars?)\b/i.test(text) || text.includes("$") ? "USD" : "USD";
  const minimum = values[0] ?? null;
  const maximum = values.length >= 2 ? values[1]! : null;
  if (minimum !== null && maximum !== null && minimum > maximum) {
    return { minimum: maximum, maximum: minimum, currency, period };
  }
  return { minimum, maximum, currency, period };
}

function addRequirement(
  destination: EmployerRequirement[],
  candidate: EmployerRequirement,
): void {
  const duplicate = destination.some(
    (item) =>
      item.kind === candidate.kind &&
      item.semanticType === candidate.semanticType &&
      normalize(item.sourceText) === normalize(candidate.sourceText),
  );
  if (!duplicate) destination.push(candidate);
}

export function extractEmployerRequirements(
  page: ApplicationPage,
): EmployerRequirement[] {
  const requirements: EmployerRequirement[] = [];

  for (const segment of pageSegments(page)) {
    const text = normalize(segment.text);

    if (
      /\b(?:do(?:es)? not|doesn['’]t|will not|won['’]t|cannot|can['’]t|unable to)\s+(?:provide|offer|support|sponsor)\b.{0,80}\b(?:visa |employment )?sponsor(?:ship|ing)?\b/.test(
        text,
      ) ||
      /\bmust not require\b.{0,80}\bsponsor(?:ship|ing)?\b/.test(text) ||
      /\bno (?:visa |employment )?sponsor(?:ship|ing)?\b/.test(text)
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "SPONSORSHIP",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "SPONSORSHIP_FUTURE",
          expectedValues: ["No"],
          numericValue: null,
          unit: null,
          confidence: 0.99,
          consequential: true,
          knockout: true,
        }),
      );
    }

    if (
      /\b(?:must|need to|required to|requirement(?: is|:)?|applicants? must)\b.{0,80}\b(?:be )?(?:legally )?authorized to work\b/.test(
        text,
      ) ||
      /\bwork authorization (?:is )?required\b/.test(text)
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "WORK_AUTHORIZATION",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "WORK_AUTHORIZATION_CURRENT",
          expectedValues: ["Yes"],
          numericValue: null,
          unit: null,
          confidence: 0.98,
          consequential: true,
          knockout: true,
        }),
      );
    }

    if (
      /\b(?:u\.?s\.?|united states) citizenship (?:is )?(?:required|mandatory)\b/.test(
        text,
      ) ||
      /\bmust be (?:a )?(?:u\.?s\.?|united states) citizen\b/.test(text)
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "CITIZENSHIP",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: null,
          expectedValues: ["US_CITIZEN"],
          numericValue: null,
          unit: null,
          confidence: 0.99,
          consequential: true,
          knockout: true,
        }),
      );
    }

    const clearance = text.match(
      /\b(?:active |current )?((?:top secret|secret|public trust|ts\/sci)[^.;,]{0,40})\s+(?:clearance )?(?:is )?(?:required|mandatory)\b/,
    );
    if (
      clearance ||
      /\bmust (?:hold|have|possess)\b.{0,50}\bsecurity clearance\b/.test(text)
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "SECURITY_CLEARANCE",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "SECURITY_CLEARANCE",
          expectedValues: [compact(clearance?.[1] ?? "Security clearance")],
          numericValue: null,
          unit: null,
          confidence: clearance ? 0.97 : 0.93,
          consequential: true,
          knockout: true,
        }),
      );
    }

    const degree = text.match(
      /\b(?:bachelor(?:['’]s)?|master(?:['’]s)?|doctorate|doctoral|ph\.?d\.?|associate(?:['’]s)?)\b.{0,80}\b(?:degree )?(?:required|minimum|mandatory)\b/,
    );
    if (degree) {
      addRequirement(
        requirements,
        requirement({
          kind: "DEGREE",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "DEGREE",
          expectedValues: [
            compact(degree[0].match(/^[^.;,]{0,80}/)?.[0] ?? degree[0]),
          ],
          numericValue: null,
          unit: null,
          confidence: 0.95,
          consequential: true,
          knockout: true,
        }),
      );
    }

    const experience = text.match(
      /\b(?:minimum (?:of )?|at least |requires? |required:?\s*)?(\d+(?:\.\d+)?)\+?\s+years?\b.{0,100}\b(?:experience|professional|work)\b/,
    );
    if (
      experience &&
      /\b(required|minimum|at least|must|requires?)\b/.test(text)
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "EXPERIENCE",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "RELEVANT_EXPERIENCE",
          expectedValues: [],
          numericValue: Number(experience[1]),
          unit: "YEARS",
          confidence: 0.94,
          consequential: true,
          knockout: true,
        }),
      );
    }

    const salary = parseSalaryRange(segment.text);
    if (
      salary &&
      /\b(?:salary|pay|compensation|base|hourly|annual|yearly)\b/.test(text)
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "SALARY",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "SALARY_EXPECTATION",
          expectedValues: [],
          numericValue: salary.minimum,
          unit: `${salary.currency}_${salary.period}`,
          confidence: 0.92,
          consequential: false,
          knockout: false,
        }),
      );
    }

    const travel = text.match(
      /\b(?:must be willing to|required to|requires?)\b.{0,50}\btravel\b(?:\s+(?:up to )?(\d{1,3})\s*%)?/,
    );
    if (travel) {
      addRequirement(
        requirements,
        requirement({
          kind: "TRAVEL",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "TRAVEL",
          expectedValues: ["Yes"],
          numericValue: travel[1] ? Number(travel[1]) : null,
          unit: travel[1] ? "PERCENT" : null,
          confidence: 0.91,
          consequential: false,
          knockout: false,
        }),
      );
    }

    if (
      /\b(?:must be willing to|required to|must)\b.{0,50}\brelocat(?:e|ion)\b/.test(
        text,
      )
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "RELOCATION",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "RELOCATION",
          expectedValues: ["Yes"],
          numericValue: null,
          unit: null,
          confidence: 0.93,
          consequential: false,
          knockout: false,
        }),
      );
    }

    if (
      /\b(?:onsite|on-site|in office)\b.{0,45}\b(?:required|mandatory|must)\b/.test(
        text,
      )
    ) {
      addRequirement(
        requirements,
        requirement({
          kind: "WORK_MODE",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "ONSITE",
          expectedValues: ["Onsite"],
          numericValue: null,
          unit: null,
          confidence: 0.9,
          consequential: false,
          knockout: false,
        }),
      );
    }

    const start = text.match(
      /\b(?:must|need to|required to)\b.{0,50}\bstart\b.{0,30}\b(?:by|on)\s+([^.;,]{3,40})/,
    );
    if (start) {
      addRequirement(
        requirements,
        requirement({
          kind: "START_DATE",
          sourceKind: segment.sourceKind,
          sourceText: segment.text,
          semanticType: "START_DATE",
          expectedValues: [compact(start[1])],
          numericValue: null,
          unit: null,
          confidence: 0.9,
          consequential: false,
          knockout: false,
        }),
      );
    }
  }

  return requirements.sort(
    (left, right) =>
      left.kind.localeCompare(right.kind) ||
      left.requirementId.localeCompare(right.requirementId),
  );
}

function factValue(fact: ProfileFact | undefined): string | null {
  if (!fact) return null;
  return Array.isArray(fact.value) ? fact.value.join(", ") : String(fact.value);
}

function authoritativeFact(
  profile: ProfileLike,
  key: string,
): ProfileFact | null {
  const fact = profile.facts.find((candidate) => candidate.key === key);
  if (!fact || !authoritativeTrust.has(fact.trustLevel)) return null;
  if (fact.protected && !fact.confirmedAt) return null;
  return fact;
}

function syntheticQuestion(requirement: EmployerRequirement): Question | null {
  if (!requirement.semanticType) return null;
  return {
    questionId: `requirement-${requirement.requirementId}`,
    controlId: `requirement-${requirement.requirementId}`,
    rawText: requirement.sourceText,
    semanticType: requirement.semanticType,
    confidence: requirement.confidence,
    sensitive: requirement.consequential,
    requiresReview: requirement.consequential,
  };
}

function booleanValue(value: string | null): "YES" | "NO" | "UNKNOWN" {
  const text = normalize(value ?? "");
  if (/^(yes|true|authorized|eligible|will|willing)$/.test(text)) return "YES";
  if (/^(no|false|not authorized|not eligible|none|never)$/.test(text))
    return "NO";
  if (
    /\b(?:do not|don['’]t|does not|doesn['’]t|will not|won['’]t|no)\b/.test(
      text,
    )
  )
    return "NO";
  if (/\b(?:yes|require|requires|authorized|eligible|willing)\b/.test(text))
    return "YES";
  return "UNKNOWN";
}

function finding(
  requirement: EmployerRequirement,
  state: EmployerPreflightFindingState,
  candidateValue: string | null,
  reason: string,
): EmployerPreflightFinding {
  return { requirement, state, candidateValue, reason };
}

function expectedBooleanFinding(
  requirement: EmployerRequirement,
  value: string | null,
): EmployerPreflightFinding {
  const actual = booleanValue(value);
  const expected = requirement.expectedValues[0]?.toLocaleUpperCase("en-US");
  if (actual === "UNKNOWN") {
    return finding(
      requirement,
      requirement.knockout ? "UNRESOLVED" : "REVIEW",
      value,
      "Candidate value is not a deterministic yes/no answer",
    );
  }
  const matches =
    (expected === "YES" && actual === "YES") ||
    (expected === "NO" && actual === "NO");
  return finding(
    requirement,
    matches ? "READY" : requirement.knockout ? "BLOCKED" : "REVIEW",
    value,
    matches
      ? "Confirmed candidate value satisfies the explicit employer requirement"
      : "Confirmed candidate value conflicts with the explicit employer requirement",
  );
}

function degreeRank(value: string | null): number | null {
  const text = normalize(value ?? "");
  if (/\b(ph\.?d\.?|doctorate|doctoral)\b/.test(text)) return 4;
  if (/\bmaster(?:['’]s)?\b/.test(text)) return 3;
  if (/\bbachelor(?:['’]s)?\b/.test(text)) return 2;
  if (/\bassociate(?:['’]s)?\b/.test(text)) return 1;
  return null;
}

function resolveMappedRequirement(
  requirement: EmployerRequirement,
  profile: ProfileLike,
): AnswerResolution | null {
  const question = syntheticQuestion(requirement);
  return question ? resolveProfileAnswer(question, profile) : null;
}

export function evaluateEmployerRequirement(
  requirement: EmployerRequirement,
  profile: ProfileLike,
): EmployerPreflightFinding {
  if (
    requirement.kind === "WORK_AUTHORIZATION" ||
    requirement.kind === "SPONSORSHIP"
  ) {
    const resolution = resolveMappedRequirement(requirement, profile);
    if (!resolution?.value) {
      return finding(
        requirement,
        "UNRESOLVED",
        null,
        "A confirmed candidate answer is required for this explicit knockout rule",
      );
    }
    if (resolution.state === "REVIEW") {
      return finding(
        requirement,
        "REVIEW",
        resolution.value,
        resolution.reasons.join("; ") || "Candidate answer requires review",
      );
    }
    return expectedBooleanFinding(requirement, resolution.value);
  }

  if (requirement.kind === "CITIZENSHIP") {
    const fact =
      authoritativeFact(profile, "citizenship") ??
      authoritativeFact(profile, "citizenship_status");
    const value = factValue(fact ?? undefined);
    if (!value) {
      return finding(
        requirement,
        "UNRESOLVED",
        null,
        "US citizenship is explicitly required but no confirmed citizenship fact is available",
      );
    }
    const matches = /\b(?:u\.?s\.?|united states) citizen\b/i.test(value);
    return finding(
      requirement,
      matches ? "READY" : "BLOCKED",
      value,
      matches
        ? "Confirmed citizenship satisfies the explicit requirement"
        : "Confirmed citizenship does not satisfy the explicit requirement",
    );
  }

  if (requirement.kind === "SECURITY_CLEARANCE") {
    const resolution = resolveMappedRequirement(requirement, profile);
    const value = resolution?.value ?? null;
    if (!value) {
      return finding(
        requirement,
        "UNRESOLVED",
        null,
        "A confirmed security-clearance fact is required",
      );
    }
    if (/\b(?:none|no clearance|not cleared|do not have)\b/i.test(value)) {
      return finding(
        requirement,
        "BLOCKED",
        value,
        "Confirmed clearance status conflicts with the explicit clearance requirement",
      );
    }
    return finding(
      requirement,
      resolution?.state === "READY" ? "READY" : "REVIEW",
      value,
      "A security-clearance requirement was detected and the saved clearance should be verified against its exact level",
    );
  }

  if (requirement.kind === "DEGREE") {
    const resolution = resolveMappedRequirement(requirement, profile);
    const candidateRank = degreeRank(resolution?.value ?? null);
    const requiredRank = degreeRank(requirement.sourceText);
    if (candidateRank === null || requiredRank === null) {
      return finding(
        requirement,
        "UNRESOLVED",
        resolution?.value ?? null,
        "Degree requirement or confirmed candidate degree could not be normalized safely",
      );
    }
    return finding(
      requirement,
      candidateRank >= requiredRank ? "READY" : "BLOCKED",
      resolution?.value ?? null,
      candidateRank >= requiredRank
        ? "Confirmed degree level meets or exceeds the explicit minimum"
        : "Confirmed degree level is below the explicit minimum",
    );
  }

  if (requirement.kind === "EXPERIENCE") {
    const fact =
      authoritativeFact(profile, "years_experience") ??
      authoritativeFact(profile, "total_years_experience");
    const value = factValue(fact ?? undefined);
    const candidateYears = value ? parseNumber(value) : null;
    if (candidateYears === null || requirement.numericValue === null) {
      return finding(
        requirement,
        "REVIEW",
        value,
        "An explicit experience threshold exists, but MUNSHI will not infer total tenure from résumé dates without a verified calculation",
      );
    }
    return finding(
      requirement,
      candidateYears >= requirement.numericValue ? "READY" : "BLOCKED",
      value,
      candidateYears >= requirement.numericValue
        ? "Verified total experience meets the explicit threshold"
        : "Verified total experience is below the explicit threshold",
    );
  }

  if (requirement.kind === "SALARY") {
    const employer = parseSalaryRange(requirement.sourceText);
    const candidateFact = authoritativeFact(profile, "salary_expectation");
    const candidate = parseSalaryRange(
      factValue(candidateFact ?? undefined) ?? "",
    );
    const evaluation = evaluateSalaryRanges(candidate, employer);
    return finding(
      requirement,
      evaluation.state,
      factValue(candidateFact ?? undefined),
      evaluation.reason,
    );
  }

  if (requirement.kind === "START_DATE") {
    const fact = authoritativeFact(profile, "earliest_start_date");
    const candidateValue = factValue(fact ?? undefined);
    const candidate = candidateValue ? Date.parse(candidateValue) : Number.NaN;
    const expected = requirement.expectedValues[0]
      ? Date.parse(requirement.expectedValues[0])
      : Number.NaN;
    if (Number.isNaN(candidate) || Number.isNaN(expected)) {
      return finding(
        requirement,
        "REVIEW",
        candidateValue,
        "Start-date requirement needs date review because one side could not be parsed safely",
      );
    }
    return finding(
      requirement,
      candidate <= expected ? "READY" : "BLOCKED",
      candidateValue,
      candidate <= expected
        ? "Confirmed earliest start date satisfies the explicit start-by date"
        : "Confirmed earliest start date is later than the explicit start-by date",
    );
  }

  if (requirement.kind === "RELOCATION" || requirement.kind === "TRAVEL") {
    const resolution = resolveMappedRequirement(requirement, profile);
    if (!resolution?.value) {
      return finding(
        requirement,
        "REVIEW",
        null,
        "Employer preference requirement is explicit but the candidate preference is not confirmed",
      );
    }
    return expectedBooleanFinding(requirement, resolution.value);
  }

  if (requirement.kind === "WORK_MODE") {
    const fact = authoritativeFact(profile, "preferred_work_mode");
    const value = factValue(fact ?? undefined);
    if (!value) {
      return finding(
        requirement,
        "REVIEW",
        null,
        "Onsite requirement should be compared with the owner-confirmed work-mode preference",
      );
    }
    return finding(
      requirement,
      /\b(on[- ]?site|onsite|any|flexible)\b/i.test(value) ? "READY" : "REVIEW",
      value,
      /\b(on[- ]?site|onsite|any|flexible)\b/i.test(value)
        ? "Saved work-mode preference is compatible with the explicit onsite requirement"
        : "Saved work-mode preference may conflict with the explicit onsite requirement; owner review is required",
    );
  }

  return finding(
    requirement,
    "REVIEW",
    null,
    "Employer requirement needs owner review",
  );
}

export function buildEmployerPreflightReport(
  page: ApplicationPage,
  profile: ProfileLike,
): EmployerPreflightReport {
  const requirements = extractEmployerRequirements(page);
  const findings = requirements.map((item) =>
    evaluateEmployerRequirement(item, profile),
  );
  const gate = summarizePreflightGate(
    findings.map((item) => ({
      id: item.requirement.requirementId,
      state: item.state,
    })),
  );
  return { requirements, findings, gate };
}

/**
 * Current-page knockout checking is intentionally narrower than the full job
 * pre-flight report. AutoPilot hard-blocks only when the current application
 * question has an owner-approved answer that deterministically contradicts an
 * explicit employer rule. Requirements that have not reached a current form
 * question remain intelligence/review signals instead of deadlocking progress.
 */
export function evaluateCurrentPageKnockouts(
  page: ApplicationPage,
  answers: Record<string, EmployerAnswer>,
): EmployerPreflightFinding[] {
  const requirements = extractEmployerRequirements(page).filter(
    (item) =>
      item.knockout &&
      (item.kind === "SPONSORSHIP" || item.kind === "WORK_AUTHORIZATION"),
  );
  const findings: EmployerPreflightFinding[] = [];
  for (const item of requirements) {
    const question = page.questions.find(
      (candidate) => candidate.semanticType === item.semanticType,
    );
    if (!question) continue;
    const answer = answers[question.questionId];
    if (!answer?.approved || !compact(answer.value)) continue;
    findings.push(expectedBooleanFinding(item, answer.value));
  }
  return findings;
}
