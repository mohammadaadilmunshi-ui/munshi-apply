import type { JobSignalReport } from "./job-signals";

export type OpportunityPreflightState =
  "READY" | "REVIEW" | "UNRESOLVED" | "BLOCKED";

export type OpportunityCompatibility =
  "MATCH" | "PARTIAL" | "MISMATCH" | "UNKNOWN";

export type OpportunityPriority =
  "HIGH" | "MEDIUM" | "LOW" | "HOLD" | "INSUFFICIENT_DATA";

export type OpportunityFitFacts = {
  roleMatchScore?: number | null;
  evidenceMatchScore?: number | null;
  locationCompatibility?: OpportunityCompatibility | null;
  workAuthorizationCompatibility?: OpportunityCompatibility | null;
  compensationCompatibility?: OpportunityCompatibility | null;
  ownerPriority?: "HIGH" | "NORMAL" | "LOW" | null;
};

export type JobOpportunityAssessment = {
  priority: OpportunityPriority;
  priorityScore: number | null;
  confidence: number;
  positiveFactors: readonly string[];
  riskFactors: readonly string[];
  unknowns: readonly string[];
  explanation: string;
};

type ScoredFactor = {
  label: string;
  score: number;
  weight: number;
};

function boundedScore(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(
      "Opportunity fit scores must be finite numbers from 0 to 100",
    );
  }
  return Math.round(value);
}

function compatibilityScore(
  value: OpportunityCompatibility | null | undefined,
): number | null {
  switch (value ?? "UNKNOWN") {
    case "MATCH":
      return 100;
    case "PARTIAL":
      return 60;
    case "MISMATCH":
      return 0;
    case "UNKNOWN":
      return null;
  }
}

function signalCoverage(report: JobSignalReport): number {
  const values = Object.values(report.dimensions);
  if (values.length === 0) return 0;
  return (
    values.filter((dimension) => dimension.score !== null).length /
    values.length
  );
}

function weightedAverage(factors: readonly ScoredFactor[]): number | null {
  if (!factors.length) return null;
  const weight = factors.reduce((total, factor) => total + factor.weight, 0);
  if (weight <= 0) return null;
  return (
    factors.reduce((total, factor) => total + factor.score * factor.weight, 0) /
    weight
  );
}

function addCompatibilityFactor(input: {
  factors: ScoredFactor[];
  positives: string[];
  risks: string[];
  unknowns: string[];
  label: string;
  value: OpportunityCompatibility | null | undefined;
  weight: number;
  unknownMessage: string;
}): void {
  const normalized = input.value ?? "UNKNOWN";
  const score = compatibilityScore(normalized);
  if (score === null) {
    input.unknowns.push(input.unknownMessage);
    return;
  }
  input.factors.push({ label: input.label, score, weight: input.weight });
  if (normalized === "MATCH") {
    input.positives.push(`${input.label} is a verified match.`);
  } else if (normalized === "PARTIAL") {
    input.risks.push(`${input.label} is only a partial match.`);
  } else {
    input.risks.push(`${input.label} is a verified mismatch.`);
  }
}

export function assessJobOpportunity(input: {
  jobSignals: JobSignalReport;
  preflightState: OpportunityPreflightState;
  fit?: OpportunityFitFacts | null;
}): JobOpportunityAssessment {
  const fit = input.fit ?? {};
  const factors: ScoredFactor[] = [];
  const positiveFactors: string[] = [];
  const riskFactors: string[] = [];
  const unknowns: string[] = [];

  const roleMatch = boundedScore(fit.roleMatchScore);
  if (roleMatch === null) {
    unknowns.push(
      "Role-family fit has not been evaluated from verified evidence.",
    );
  } else {
    factors.push({ label: "Role fit", score: roleMatch, weight: 1.25 });
    if (roleMatch >= 75)
      positiveFactors.push("Verified role-family fit is strong.");
    else if (roleMatch < 50)
      riskFactors.push("Verified role-family fit is limited.");
  }

  const evidenceMatch = boundedScore(fit.evidenceMatchScore);
  if (evidenceMatch === null) {
    unknowns.push("Evidence coverage for the posting has not been evaluated.");
  } else {
    factors.push({ label: "Evidence fit", score: evidenceMatch, weight: 1.5 });
    if (evidenceMatch >= 75) {
      positiveFactors.push("Verified experience/evidence coverage is strong.");
    } else if (evidenceMatch < 50) {
      riskFactors.push("Verified experience/evidence coverage is limited.");
    }
  }

  addCompatibilityFactor({
    factors,
    positives: positiveFactors,
    risks: riskFactors,
    unknowns,
    label: "Location/work-mode compatibility",
    value: fit.locationCompatibility,
    weight: 1,
    unknownMessage: "Location/work-mode compatibility is unknown.",
  });
  addCompatibilityFactor({
    factors,
    positives: positiveFactors,
    risks: riskFactors,
    unknowns,
    label: "Work-authorization compatibility",
    value: fit.workAuthorizationCompatibility,
    weight: 1.5,
    unknownMessage: "Work-authorization compatibility is unknown.",
  });
  addCompatibilityFactor({
    factors,
    positives: positiveFactors,
    risks: riskFactors,
    unknowns,
    label: "Compensation compatibility",
    value: fit.compensationCompatibility,
    weight: 0.75,
    unknownMessage: "Compensation compatibility is unknown.",
  });

  const signalConcern = input.jobSignals.overallScore;
  if (signalConcern === null) {
    unknowns.push(
      "The posting does not contain enough evidence for an overall Job Signal concern score.",
    );
  } else if (signalConcern >= 65) {
    riskFactors.push(
      `Evidence-backed Job Signal concern is high (${signalConcern}/100).`,
    );
  } else if (signalConcern <= 30) {
    positiveFactors.push(
      `Evidence-backed Job Signal concern is low (${signalConcern}/100).`,
    );
  }

  const workAuthorizationRisk =
    input.jobSignals.dimensions.WORK_AUTHORIZATION_RISK.score;
  const workAuthorizationCompatibility =
    fit.workAuthorizationCompatibility ?? "UNKNOWN";

  if (input.preflightState === "BLOCKED") {
    riskFactors.unshift(
      "Employer pre-flight contains a verified blocking contradiction.",
    );
    return {
      priority: "HOLD",
      priorityScore: 0,
      confidence: 1,
      positiveFactors,
      riskFactors,
      unknowns,
      explanation:
        "Hold this opportunity because employer pre-flight contains a verified contradiction. Job Signal scoring cannot override deterministic eligibility facts.",
    };
  }

  if (input.preflightState === "UNRESOLVED") {
    riskFactors.unshift(
      "Employer pre-flight still contains consequential unresolved requirements.",
    );
    return {
      priority: "HOLD",
      priorityScore: null,
      confidence: 0.9,
      positiveFactors,
      riskFactors,
      unknowns,
      explanation:
        "Hold for owner review until consequential employer requirements are resolved. MUNSHI does not guess eligibility to create a priority score.",
    };
  }

  if (workAuthorizationCompatibility === "MISMATCH") {
    riskFactors.unshift(
      "Verified work-authorization compatibility is a mismatch.",
    );
    return {
      priority: "HOLD",
      priorityScore: 0,
      confidence: 1,
      positiveFactors,
      riskFactors,
      unknowns,
      explanation:
        "Hold because verified work-authorization facts conflict with the opportunity. Narrative fit and Job Signals cannot override that mismatch.",
    };
  }

  if (
    workAuthorizationRisk !== null &&
    workAuthorizationRisk >= 65 &&
    workAuthorizationCompatibility === "UNKNOWN"
  ) {
    riskFactors.unshift(
      "The posting contains consequential work-authorization language that has not been matched to verified owner facts.",
    );
    return {
      priority: "HOLD",
      priorityScore: null,
      confidence: Math.max(0.75, signalCoverage(input.jobSignals)),
      positiveFactors,
      riskFactors,
      unknowns,
      explanation:
        "Hold for work-authorization review. The posting contains consequential language and MUNSHI will not infer compatibility from incomplete facts.",
    };
  }

  const fitAverage = weightedAverage(factors);
  if (fitAverage === null) {
    return {
      priority: "INSUFFICIENT_DATA",
      priorityScore: null,
      confidence: Number((signalCoverage(input.jobSignals) * 0.35).toFixed(3)),
      positiveFactors,
      riskFactors,
      unknowns,
      explanation:
        "There is not enough verified fit information to prioritize this opportunity. Job Signals alone describe posting evidence; they are not a substitute for candidate fit.",
    };
  }

  let score = fitAverage;
  if (signalConcern !== null) score -= signalConcern * 0.25;
  if (input.preflightState === "REVIEW") score -= 8;
  if (fit.ownerPriority === "HIGH") score += 8;
  if (fit.ownerPriority === "LOW") score -= 8;
  score = Math.max(0, Math.min(100, Math.round(score)));

  const knownFitFactors = factors.length;
  const fitCoverage = Math.min(1, knownFitFactors / 5);
  const confidence = Number(
    Math.min(
      1,
      fitCoverage * 0.7 + signalCoverage(input.jobSignals) * 0.3,
    ).toFixed(3),
  );
  const priority: OpportunityPriority =
    score >= 72 ? "HIGH" : score >= 50 ? "MEDIUM" : "LOW";

  if (input.preflightState === "REVIEW") {
    riskFactors.push(
      "Employer pre-flight still requires owner review before automated navigation.",
    );
  }

  return {
    priority,
    priorityScore: score,
    confidence,
    positiveFactors,
    riskFactors,
    unknowns,
    explanation:
      "Priority combines verified fit facts, deterministic pre-flight state, and evidence-backed Job Signal concerns. It is decision support, not an instruction to submit an application.",
  };
}
