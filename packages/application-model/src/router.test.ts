import { describe, expect, it } from "vitest";
import type { BudgetDecision } from "./budget";
import { routeIntelligence, type RouterInput } from "./router";

const allowedBudget: BudgetDecision = {
  state: "ALLOW",
  month: "2026-08",
  spentUsd: 0,
  plannedCostUsd: 0.01,
  projectedUsd: 0.01,
  remainingUsd: 9.99,
  reason: "within budget",
};

function input(overrides: Partial<RouterInput> = {}): RouterInput {
  return {
    task: "SHORT_GENERATION",
    deterministicAvailable: false,
    savedKnowledgeAvailable: false,
    savedKnowledgeAuthoritative: false,
    protectedOrSensitive: false,
    aiEnabled: true,
    credentialConfigured: true,
    cheapModel: "cheap-model",
    strongModel: "strong-model",
    budget: allowedBudget,
    ...overrides,
  };
}

describe("routeIntelligence", () => {
  it("prefers deterministic resolution before every other lane", () => {
    const decision = routeIntelligence(
      input({
        deterministicAvailable: true,
        savedKnowledgeAvailable: true,
        savedKnowledgeAuthoritative: true,
        protectedOrSensitive: true,
      }),
    );

    expect(decision.route).toBe("DETERMINISTIC");
    expect(decision.model).toBeNull();
    expect(decision.generatedOutputRequiresValidation).toBe(false);
  });

  it("uses only authoritative saved knowledge", () => {
    expect(
      routeIntelligence(
        input({
          savedKnowledgeAvailable: true,
          savedKnowledgeAuthoritative: true,
        }),
      ).route,
    ).toBe("SAVED_KNOWLEDGE");

    expect(
      routeIntelligence(
        input({
          savedKnowledgeAvailable: true,
          savedKnowledgeAuthoritative: false,
        }),
      ).route,
    ).toBe("CHEAP_MODEL");
  });

  it("never sends protected or sensitive choices to a model", () => {
    const decision = routeIntelligence(
      input({
        task: "COMPLEX_REASONING",
        protectedOrSensitive: true,
      }),
    );

    expect(decision.route).toBe("MANUAL");
    expect(decision.reason).toContain("must not be inferred");
  });

  it("uses the cheap lane for classification and short generation", () => {
    for (const task of [
      "CLASSIFY",
      "FACT_LOOKUP",
      "SHORT_GENERATION",
    ] as const) {
      const decision = routeIntelligence(input({ task }));
      expect(decision.route).toBe("CHEAP_MODEL");
      expect(decision.model).toBe("cheap-model");
      expect(decision.generatedOutputRequiresValidation).toBe(true);
    }
  });

  it("uses the strong lane for complex reasoning and image inspection", () => {
    for (const task of ["COMPLEX_REASONING", "IMAGE_INSPECTION"] as const) {
      const decision = routeIntelligence(input({ task }));
      expect(decision.route).toBe("STRONG_MODEL");
      expect(decision.model).toBe("strong-model");
      expect(decision.generatedOutputRequiresValidation).toBe(true);
    }
  });

  it("blocks model routing at the budget hard stop", () => {
    const decision = routeIntelligence(
      input({
        budget: {
          ...allowedBudget,
          state: "BLOCK",
          reason: "hard stop reached",
        },
      }),
    );

    expect(decision.route).toBe("MANUAL");
    expect(decision.reason).toBe("hard stop reached");
  });

  it("requires acknowledgement when the budget is in warning state", () => {
    const decision = routeIntelligence(
      input({
        budget: {
          ...allowedBudget,
          state: "WARN",
          reason: "warning threshold reached",
        },
      }),
    );

    expect(decision.route).toBe("CHEAP_MODEL");
    expect(decision.requiresBudgetAcknowledgement).toBe(true);
  });

  it("fails closed when the required model lane is not configured", () => {
    expect(routeIntelligence(input({ cheapModel: "" })).route).toBe("MANUAL");
    expect(
      routeIntelligence(input({ task: "COMPLEX_REASONING", strongModel: "" }))
        .route,
    ).toBe("MANUAL");
  });
});
