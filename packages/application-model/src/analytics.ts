export type ApplicationOutcomeStage =
  "APPLIED" | "ASSESSMENT" | "INTERVIEW" | "OFFER" | "REJECTED" | "WITHDRAWN";

export type ApplicationOutcomeEvent = {
  eventId: string;
  applicationId: string;
  stage: ApplicationOutcomeStage;
  occurredAt: string;
  source: string;
};

export type ExperimentVariant = {
  variantId: string;
  label: string;
  weight: number;
};

export type ExperimentDefinition = {
  experimentId: string;
  label: string;
  variants: readonly ExperimentVariant[];
  minimumSamplePerVariant: number;
  status: "DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETE";
};

export type ExperimentAssignment = {
  experimentId: string;
  subjectId: string;
  variantId: string;
};

export type VariantOutcomeSummary = {
  variantId: string;
  assignedCount: number;
  positiveOutcomeCount: number;
  positiveOutcomeRate: number | null;
};

export type ExperimentSummary = {
  experimentId: string;
  analysisReady: boolean;
  reason: string;
  variants: readonly VariantOutcomeSummary[];
};

function stableHash(value: string): number {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return result >>> 0;
}

function validateExperiment(experiment: ExperimentDefinition): void {
  if (!experiment.experimentId.trim() || !experiment.label.trim()) {
    throw new Error("Experiment id and label are required");
  }
  if (
    !Number.isSafeInteger(experiment.minimumSamplePerVariant) ||
    experiment.minimumSamplePerVariant < 1
  ) {
    throw new Error("minimumSamplePerVariant must be a positive integer");
  }
  if (experiment.variants.length < 2) {
    throw new Error("Experiment requires at least two variants");
  }
  const ids = new Set<string>();
  for (const variant of experiment.variants) {
    if (!variant.variantId.trim() || !variant.label.trim()) {
      throw new Error("Variant id and label are required");
    }
    if (ids.has(variant.variantId))
      throw new Error("Variant ids must be unique");
    ids.add(variant.variantId);
    if (!Number.isFinite(variant.weight) || variant.weight <= 0) {
      throw new Error("Variant weights must be positive finite numbers");
    }
  }
}

export function assignExperimentVariant(input: {
  experiment: ExperimentDefinition;
  subjectId: string;
  assignmentSalt: string;
}): ExperimentAssignment {
  validateExperiment(input.experiment);
  if (input.experiment.status !== "ACTIVE") {
    throw new Error("Experiment must be active before assignment");
  }
  if (!input.subjectId.trim() || !input.assignmentSalt.trim()) {
    throw new Error("Subject id and assignment salt are required");
  }
  const totalWeight = input.experiment.variants.reduce(
    (total, variant) => total + variant.weight,
    0,
  );
  const draw =
    (stableHash(
      `${input.assignmentSalt}|${input.experiment.experimentId}|${input.subjectId}`,
    ) /
      0x1_0000_0000) *
    totalWeight;
  let cursor = 0;
  let selected = input.experiment.variants.at(-1)!;
  for (const variant of input.experiment.variants) {
    cursor += variant.weight;
    if (draw < cursor) {
      selected = variant;
      break;
    }
  }
  return {
    experimentId: input.experiment.experimentId,
    subjectId: input.subjectId,
    variantId: selected.variantId,
  };
}

const positiveStages = new Set<ApplicationOutcomeStage>([
  "ASSESSMENT",
  "INTERVIEW",
  "OFFER",
]);

export function summarizeExperiment(input: {
  experiment: ExperimentDefinition;
  assignments: readonly ExperimentAssignment[];
  outcomesBySubject: ReadonlyMap<string, readonly ApplicationOutcomeEvent[]>;
}): ExperimentSummary {
  validateExperiment(input.experiment);
  const variants = input.experiment.variants.map((variant) => {
    const assignments = input.assignments.filter(
      (assignment) =>
        assignment.experimentId === input.experiment.experimentId &&
        assignment.variantId === variant.variantId,
    );
    const positiveOutcomeCount = assignments.filter((assignment) =>
      (input.outcomesBySubject.get(assignment.subjectId) ?? []).some((event) =>
        positiveStages.has(event.stage),
      ),
    ).length;
    return {
      variantId: variant.variantId,
      assignedCount: assignments.length,
      positiveOutcomeCount,
      positiveOutcomeRate:
        assignments.length === 0
          ? null
          : Number((positiveOutcomeCount / assignments.length).toFixed(6)),
    } satisfies VariantOutcomeSummary;
  });

  const analysisReady = variants.every(
    (variant) =>
      variant.assignedCount >= input.experiment.minimumSamplePerVariant,
  );
  return {
    experimentId: input.experiment.experimentId,
    analysisReady,
    reason: analysisReady
      ? "Minimum sample gate is satisfied; rates may be compared descriptively without implying causality"
      : "Minimum sample gate is not satisfied; do not label a variant a winner",
    variants,
  };
}

export function validateOpaqueAttributionToken(token: string): boolean {
  return /^[A-Za-z0-9_-]{8,64}$/.test(token);
}
