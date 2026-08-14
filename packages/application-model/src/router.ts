import type { BudgetDecision } from "./budget";

export type IntelligenceTask =
  | "CLASSIFY"
  | "FACT_LOOKUP"
  | "SHORT_GENERATION"
  | "COMPLEX_REASONING"
  | "IMAGE_INSPECTION";

export type IntelligenceRoute =
  | "DETERMINISTIC"
  | "SAVED_KNOWLEDGE"
  | "CHEAP_MODEL"
  | "STRONG_MODEL"
  | "MANUAL";

export type RouterInput = {
  task: IntelligenceTask;
  deterministicAvailable: boolean;
  savedKnowledgeAvailable: boolean;
  savedKnowledgeAuthoritative: boolean;
  protectedOrSensitive: boolean;
  aiEnabled: boolean;
  credentialConfigured: boolean;
  cheapModel: string;
  strongModel: string;
  budget: BudgetDecision;
};

export type RouterDecision = {
  route: IntelligenceRoute;
  model: string | null;
  requiresBudgetAcknowledgement: boolean;
  generatedOutputRequiresValidation: boolean;
  reason: string;
};

function modelDecision(
  route: "CHEAP_MODEL" | "STRONG_MODEL",
  model: string,
  budget: BudgetDecision,
): RouterDecision {
  return {
    route,
    model,
    requiresBudgetAcknowledgement: budget.state === "WARN",
    generatedOutputRequiresValidation: true,
    reason:
      route === "CHEAP_MODEL"
        ? "No trusted local answer is available; use the configured economical model lane"
        : "No trusted local answer is available; the task requires the configured stronger model lane",
  };
}

export function routeIntelligence(input: RouterInput): RouterDecision {
  if (input.deterministicAvailable) {
    return {
      route: "DETERMINISTIC",
      model: null,
      requiresBudgetAcknowledgement: false,
      generatedOutputRequiresValidation: false,
      reason: "A deterministic resolver can answer without model inference",
    };
  }

  if (input.savedKnowledgeAvailable && input.savedKnowledgeAuthoritative) {
    return {
      route: "SAVED_KNOWLEDGE",
      model: null,
      requiresBudgetAcknowledgement: false,
      generatedOutputRequiresValidation: false,
      reason: "Authoritative saved knowledge can answer without model inference",
    };
  }

  if (input.protectedOrSensitive) {
    return {
      route: "MANUAL",
      model: null,
      requiresBudgetAcknowledgement: false,
      generatedOutputRequiresValidation: false,
      reason: "Protected or sensitive choices must not be inferred by a model",
    };
  }

  if (!input.aiEnabled || !input.credentialConfigured) {
    return {
      route: "MANUAL",
      model: null,
      requiresBudgetAcknowledgement: false,
      generatedOutputRequiresValidation: false,
      reason: "Model inference is unavailable because AI is disabled or unconfigured",
    };
  }

  if (input.budget.state === "BLOCK") {
    return {
      route: "MANUAL",
      model: null,
      requiresBudgetAcknowledgement: false,
      generatedOutputRequiresValidation: false,
      reason: input.budget.reason,
    };
  }

  const strongTask =
    input.task === "COMPLEX_REASONING" || input.task === "IMAGE_INSPECTION";
  if (strongTask) {
    if (!input.strongModel.trim()) {
      return {
        route: "MANUAL",
        model: null,
        requiresBudgetAcknowledgement: false,
        generatedOutputRequiresValidation: false,
        reason: "A stronger model is required but none is configured",
      };
    }
    return modelDecision("STRONG_MODEL", input.strongModel, input.budget);
  }

  if (!input.cheapModel.trim()) {
    return {
      route: "MANUAL",
      model: null,
      requiresBudgetAcknowledgement: false,
      generatedOutputRequiresValidation: false,
      reason: "An economical model is required but none is configured",
    };
  }
  return modelDecision("CHEAP_MODEL", input.cheapModel, input.budget);
}
