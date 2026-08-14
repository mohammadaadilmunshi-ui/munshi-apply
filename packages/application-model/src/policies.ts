import type {
  Question,
  SemanticType,
  TrustLevel,
} from "@munshi-apply/contracts";
import type { AnswerResolution } from "./resolver";

export type PreflightGateState = "READY" | "REVIEW" | "BLOCKED";

export type TrustedValue = {
  sourceId: string;
  value: string;
  trustLevel: TrustLevel;
  protected: boolean;
};

export type ContradictionFinding = {
  key: string;
  state: "CLEAR" | "REVIEW" | "BLOCKED";
  distinctValues: readonly string[];
  sourceIds: readonly string[];
  reason: string | null;
};

const authoritativeTrust = new Set<TrustLevel>([
  "VERIFIED",
  "USER_CONFIRMED",
  "DOCUMENT_CONFIRMED",
]);

function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLocaleLowerCase("en-US");
}

export function detectTrustedContradiction(
  key: string,
  values: readonly TrustedValue[],
): ContradictionFinding {
  const authoritative = values.filter((value) =>
    authoritativeTrust.has(value.trustLevel),
  );
  const byNormalized = new Map<string, TrustedValue[]>();
  for (const value of authoritative) {
    const normalized = normalize(value.value);
    if (!normalized) continue;
    const bucket = byNormalized.get(normalized) ?? [];
    bucket.push(value);
    byNormalized.set(normalized, bucket);
  }

  if (byNormalized.size <= 1) {
    return {
      key,
      state: "CLEAR",
      distinctValues: Array.from(byNormalized.keys()),
      sourceIds: authoritative.map((value) => value.sourceId),
      reason: null,
    };
  }

  const hasProtectedValue = authoritative.some((value) => value.protected);
  return {
    key,
    state: hasProtectedValue ? "BLOCKED" : "REVIEW",
    distinctValues: Array.from(byNormalized.keys()).sort(),
    sourceIds: authoritative.map((value) => value.sourceId).sort(),
    reason: hasProtectedValue
      ? "Conflicting authoritative protected facts require owner resolution"
      : "Conflicting authoritative facts require review",
  };
}

export type KnockoutRule = {
  semanticType: SemanticType;
  disqualifyingValues: readonly string[];
  source: string;
};

export type KnockoutEvaluation = {
  state: PreflightGateState;
  matchedRule: boolean;
  disqualifying: boolean;
  reason: string;
};

export function evaluateKnockoutQuestion(
  question: Question,
  resolution: AnswerResolution,
  rule: KnockoutRule | null,
): KnockoutEvaluation {
  if (resolution.state === "UNRESOLVED" || !resolution.value) {
    return {
      state: "BLOCKED",
      matchedRule: false,
      disqualifying: false,
      reason: "Required knockout-sensitive answer is unresolved",
    };
  }

  if (!rule || rule.semanticType !== question.semanticType) {
    return {
      state: "REVIEW",
      matchedRule: false,
      disqualifying: false,
      reason: "No explicit employer/job knockout rule is available",
    };
  }

  const normalizedValue = normalize(resolution.value);
  const disqualifying = rule.disqualifyingValues
    .map(normalize)
    .includes(normalizedValue);

  return {
    state: disqualifying ? "BLOCKED" : "REVIEW",
    matchedRule: true,
    disqualifying,
    reason: disqualifying
      ? `Answer matches an explicit knockout rule from ${rule.source}`
      : `Answer does not match the explicit knockout rule from ${rule.source}, but consequential answers still require review`,
  };
}

export type SalaryRange = {
  minimum: number | null;
  maximum: number | null;
  currency: string;
  period: "HOUR" | "YEAR";
};

export type SalaryEvaluation = {
  state: "UNRESOLVED" | "REVIEW";
  overlaps: boolean | null;
  reason: string;
};

function validMoney(value: number | null): boolean {
  return value === null || (Number.isFinite(value) && value >= 0);
}

export function evaluateSalaryRanges(
  candidate: SalaryRange | null,
  employer: SalaryRange | null,
): SalaryEvaluation {
  if (!candidate || !employer) {
    return {
      state: "UNRESOLVED",
      overlaps: null,
      reason: "Candidate and employer salary ranges are both required for comparison",
    };
  }
  if (
    !validMoney(candidate.minimum) ||
    !validMoney(candidate.maximum) ||
    !validMoney(employer.minimum) ||
    !validMoney(employer.maximum)
  ) {
    throw new Error("Salary ranges must contain non-negative finite values");
  }
  if (candidate.currency !== employer.currency || candidate.period !== employer.period) {
    return {
      state: "REVIEW",
      overlaps: null,
      reason: "Salary ranges use different currencies or pay periods",
    };
  }

  const candidateMin = candidate.minimum ?? Number.NEGATIVE_INFINITY;
  const candidateMax = candidate.maximum ?? Number.POSITIVE_INFINITY;
  const employerMin = employer.minimum ?? Number.NEGATIVE_INFINITY;
  const employerMax = employer.maximum ?? Number.POSITIVE_INFINITY;
  if (candidateMin > candidateMax || employerMin > employerMax) {
    throw new Error("Salary range minimum cannot exceed maximum");
  }

  const overlaps = candidateMin <= employerMax && employerMin <= candidateMax;
  return {
    state: "REVIEW",
    overlaps,
    reason: overlaps
      ? "Candidate and employer salary ranges overlap; owner review remains required"
      : "Candidate and employer salary ranges do not overlap; do not reject or alter expectations without owner review",
  };
}

export type PreflightGateItem = {
  id: string;
  state: "READY" | "REVIEW" | "UNRESOLVED" | "BLOCKED";
};

export type PreflightGateSummary = {
  state: PreflightGateState;
  readyCount: number;
  reviewCount: number;
  unresolvedCount: number;
  blockedCount: number;
  canAct: boolean;
};

export function summarizePreflightGate(
  items: readonly PreflightGateItem[],
): PreflightGateSummary {
  const readyCount = items.filter((item) => item.state === "READY").length;
  const reviewCount = items.filter((item) => item.state === "REVIEW").length;
  const unresolvedCount = items.filter(
    (item) => item.state === "UNRESOLVED",
  ).length;
  const blockedCount = items.filter((item) => item.state === "BLOCKED").length;
  const state: PreflightGateState =
    blockedCount > 0 || unresolvedCount > 0
      ? "BLOCKED"
      : reviewCount > 0
        ? "REVIEW"
        : "READY";

  return {
    state,
    readyCount,
    reviewCount,
    unresolvedCount,
    blockedCount,
    canAct: state === "READY",
  };
}
