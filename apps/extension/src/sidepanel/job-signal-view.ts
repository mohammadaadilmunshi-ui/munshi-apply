import {
  jobSignalDimensions,
  type JobOpportunityAssessment,
  type JobSignalDimension,
  type JobSignalReport,
  type OpportunityPreflightState,
} from "@munshi-apply/application-model";
import { assessJobOpportunity } from "@munshi-apply/application-model";

export type JobSignalDisposition = "POSITIVE" | "MIXED" | "CONCERN" | "UNKNOWN";

export type JobSignalViewRow = {
  dimension: JobSignalDimension;
  label: string;
  score: number | null;
  confidence: number;
  disposition: JobSignalDisposition;
  directionLabel: string;
  evidence: readonly string[];
  evidenceSources: readonly string[];
  explanations: readonly string[];
};

export type JobSignalView = {
  overallLabel: string;
  overallScore: number | null;
  rows: readonly JobSignalViewRow[];
  knownDimensionCount: number;
  unknownDimensionCount: number;
  opportunity: JobOpportunityAssessment;
};

const positiveDirection = new Set<JobSignalDimension>([
  "COMPENSATION_CLARITY",
  "SENIORITY_ALIGNMENT",
  "ROLE_STABILITY",
]);

const labels: Record<JobSignalDimension, string> = {
  ROLE_AMBIGUITY: "Role ambiguity",
  RESPONSIBILITY_BREADTH: "Responsibility breadth",
  QUALIFICATION_INFLATION: "Qualification inflation",
  WORKLOAD_PRESSURE: "Workload pressure",
  SCHEDULE_INTENSITY: "Schedule intensity",
  TRAVEL_BURDEN: "Travel burden",
  COMPENSATION_CLARITY: "Compensation clarity",
  SENIORITY_ALIGNMENT: "Seniority alignment",
  ROLE_STABILITY: "Role stability",
  LOCATION_CONSTRAINTS: "Location constraints",
  WORK_AUTHORIZATION_RISK: "Work-authorization risk",
  APPLICATION_FRICTION: "Application friction",
};

export function jobSignalDisposition(
  dimension: JobSignalDimension,
  score: number | null,
): JobSignalDisposition {
  if (score === null) return "UNKNOWN";
  if (positiveDirection.has(dimension)) {
    if (score >= 68) return "POSITIVE";
    if (score <= 35) return "CONCERN";
    return "MIXED";
  }
  if (score >= 65) return "CONCERN";
  if (score <= 30) return "POSITIVE";
  return "MIXED";
}

function directionLabel(disposition: JobSignalDisposition): string {
  switch (disposition) {
    case "POSITIVE":
      return "Helpful evidence";
    case "CONCERN":
      return "Review evidence";
    case "MIXED":
      return "Context to weigh";
    case "UNKNOWN":
      return "Not stated";
  }
}

export function buildJobSignalView(input: {
  report: JobSignalReport;
  preflightState: OpportunityPreflightState;
}): JobSignalView {
  const rows = jobSignalDimensions.map((dimension) => {
    const result = input.report.dimensions[dimension];
    const evidence = result.evidenceIds
      .map((id) =>
        input.report.signals.find((signal) => signal.signalId === id),
      )
      .filter((signal) => signal !== undefined);
    const disposition = jobSignalDisposition(dimension, result.score);
    return {
      dimension,
      label: labels[dimension],
      score: result.score,
      confidence: result.confidence,
      disposition,
      directionLabel: directionLabel(disposition),
      evidence: evidence.map((signal) => signal.evidence),
      evidenceSources: evidence.map((signal) => signal.source),
      explanations: evidence.map((signal) => signal.explanation),
    } satisfies JobSignalViewRow;
  });
  const knownDimensionCount = rows.filter((row) => row.score !== null).length;
  return {
    overallLabel:
      input.report.overallSignal === "INSUFFICIENT_DATA"
        ? "Insufficient evidence"
        : `${input.report.overallSignal.toLocaleLowerCase("en-US")} concern`,
    overallScore: input.report.overallScore,
    rows,
    knownDimensionCount,
    unknownDimensionCount: rows.length - knownDimensionCount,
    opportunity: assessJobOpportunity({
      jobSignals: input.report,
      preflightState: input.preflightState,
    }),
  };
}
