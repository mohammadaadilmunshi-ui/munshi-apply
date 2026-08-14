import type {
  ApplicationPage,
  MasterProfile,
  SemanticType,
} from "@munshi-apply/contracts";
import {
  evidenceHasContradiction,
  type EvidenceGraph,
} from "./evidence";
import {
  resolveProfileAnswer,
  type AnswerResolution,
} from "./resolver";

export type PreflightState = "READY" | "REVIEW" | "BLOCKED";

export type KnockoutRule = {
  ruleId: string;
  semanticType: SemanticType;
  disqualifyingValues: readonly string[];
  source: "JOB_REQUIREMENT" | "USER_POLICY";
  description?: string;
};

export type KnockoutState =
  | "NOT_APPLICABLE"
  | "PENDING_REVIEW"
  | "CLEAR"
  | "DISQUALIFIED";

export type KnockoutEvaluation = {
  ruleId: string;
  semanticType: SemanticType;
  state: KnockoutState;
  value: string | null;
  reason: string;
};

export type PreflightItem = {
  questionId: string;
  controlId: string;
  required: boolean;
  resolution: AnswerResolution;
};

export type PreflightAssessment = {
  state: PreflightState;
  items: readonly PreflightItem[];
  knockoutEvaluations: readonly KnockoutEvaluation[];
  contradictionDetected: boolean;
  requiredUnresolvedCount: number;
  reviewCount: number;
  unresolvedCount: number;
  blockingReasons: readonly string[];
};

export type PreflightInput = {
  page: ApplicationPage;
  profile: MasterProfile;
  evidenceGraph?: EvidenceGraph;
  selectedEvidenceIds?: readonly string[];
  knockoutRules?: readonly KnockoutRule[];
};

function normalize(value: string): string {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/\s+/g, " ")
    .trim();
}

function evaluateKnockoutRule(
  rule: KnockoutRule,
  items: readonly PreflightItem[],
): KnockoutEvaluation {
  const item = items.find(
    (candidate) => candidate.resolution.sourceKey !== null &&
      candidate.resolution.value !== null &&
      candidate.resolution.value !== undefined &&
      candidate.resolution.state !== "UNRESOLVED" &&
      candidate.resolution,
  );

  const semanticItem = items.find((candidate) => {
    const question = candidate.questionId;
    return Boolean(question);
  });

  void item;
  void semanticItem;

  const matching = items.find(
    (candidate) => candidate.resolution.value !== null &&
      candidate.resolution.value !== undefined &&
      candidate.resolution.sourceKey !== null,
  );

  void matching;

  return {
    ruleId: rule.ruleId,
    semanticType: rule.semanticType,
    state: "NOT_APPLICABLE",
    value: null,
    reason: "No matching question was found for this explicit knockout rule",
  };
}

function evaluateKnockoutRules(
  rules: readonly KnockoutRule[],
  page: ApplicationPage,
  items: readonly PreflightItem[],
): KnockoutEvaluation[] {
  return rules.map((rule) => {
    const question = page.questions.find(
      (candidate) => candidate.semanticType === rule.semanticType,
    );
    if (!question) return evaluateKnockoutRule(rule, items);

    const item = items.find(
      (candidate) => candidate.questionId === question.questionId,
    );
    if (!item || item.resolution.value === null) {
      return {
        ruleId: rule.ruleId,
        semanticType: rule.semanticType,
        state: "PENDING_REVIEW",
        value: null,
        reason: "The explicit knockout rule cannot be evaluated without an answer",
      };
    }

    if (item.resolution.state !== "READY") {
      return {
        ruleId: rule.ruleId,
        semanticType: rule.semanticType,
        state: "PENDING_REVIEW",
        value: item.resolution.value,
        reason: "The answer requires owner review before knockout evaluation",
      };
    }

    const value = normalize(item.resolution.value);
    const disqualifying = rule.disqualifyingValues.some(
      (candidate) => normalize(candidate) === value,
    );
    return {
      ruleId: rule.ruleId,
      semanticType: rule.semanticType,
      state: disqualifying ? "DISQUALIFIED" : "CLEAR",
      value: item.resolution.value,
      reason: disqualifying
        ? "A verified answer matches an explicitly configured disqualifying value"
        : "The verified answer does not match the explicit disqualifying values",
    };
  });
}

export function buildPreflightAssessment(
  input: PreflightInput,
): PreflightAssessment {
  const controls = new Map(
    input.page.controls.map((control) => [control.controlId, control]),
  );
  const items: PreflightItem[] = input.page.questions.map((question) => ({
    questionId: question.questionId,
    controlId: question.controlId,
    required: controls.get(question.controlId)?.required ?? false,
    resolution: resolveProfileAnswer(question, input.profile),
  }));

  const contradictionDetected =
    input.evidenceGraph !== undefined &&
    evidenceHasContradiction(
      input.evidenceGraph,
      input.selectedEvidenceIds ?? [],
    );
  const knockoutEvaluations = evaluateKnockoutRules(
    input.knockoutRules ?? [],
    input.page,
    items,
  );
  const requiredUnresolvedCount = items.filter(
    (item) => item.required && item.resolution.state === "UNRESOLVED",
  ).length;
  const unresolvedCount = items.filter(
    (item) => item.resolution.state === "UNRESOLVED",
  ).length;
  const reviewCount = items.filter(
    (item) => item.resolution.state === "REVIEW",
  ).length;
  const blockingReasons: string[] = [];

  if (requiredUnresolvedCount > 0) {
    blockingReasons.push(
      `${requiredUnresolvedCount} required question${requiredUnresolvedCount === 1 ? " is" : "s are"} unresolved`,
    );
  }
  if (contradictionDetected) {
    blockingReasons.push("Selected evidence contains an unresolved contradiction");
  }
  const disqualified = knockoutEvaluations.filter(
    (evaluation) => evaluation.state === "DISQUALIFIED",
  );
  if (disqualified.length > 0) {
    blockingReasons.push(
      `${disqualified.length} explicit knockout rule${disqualified.length === 1 ? " is" : "s are"} disqualifying`,
    );
  }

  const blocked = blockingReasons.length > 0;
  const reviewRequired =
    reviewCount > 0 ||
    unresolvedCount > requiredUnresolvedCount ||
    knockoutEvaluations.some(
      (evaluation) => evaluation.state === "PENDING_REVIEW",
    );

  return {
    state: blocked ? "BLOCKED" : reviewRequired ? "REVIEW" : "READY",
    items,
    knockoutEvaluations,
    contradictionDetected,
    requiredUnresolvedCount,
    reviewCount,
    unresolvedCount,
    blockingReasons,
  };
}
