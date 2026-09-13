import { describe, expect, it } from "vitest";
import {
  buildInteractionEscalationPlan,
  executableEscalationSteps,
  type InteractionEscalationContext,
} from "./interaction-escalation";

function context(
  overrides: Partial<InteractionEscalationContext> = {},
): InteractionEscalationContext {
  return {
    kind: "COMBOBOX",
    semanticType: "COUNTRY",
    sensitive: false,
    reversible: true,
    authenticationBoundary: false,
    finalSubmit: false,
    frameReachable: true,
    promotedRecipeAvailable: true,
    shadowRecipeAvailable: true,
    popupExpected: true,
    popupOwned: true,
    keyboardOperable: true,
    visualFallbackEnabled: true,
    ...overrides,
  };
}

describe("interaction escalation", () => {
  it("orders verified recipes before generic and visual fallbacks", () => {
    const steps = executableEscalationSteps(
      buildInteractionEscalationPlan(context()),
    );

    expect(steps.map((step) => step.strategy)).toEqual([
      "PROMOTED_RECIPE",
      "NATIVE_CONTROL",
      "ARIA_PATTERN",
      "KEYBOARD_PATTERN",
      "STRUCTURAL_POPUP",
      "STATE_TRANSITION",
      "SHADOW_RECIPE",
      "VISUAL_ASSISTED_CONTROL",
    ]);
    expect(steps.every((step) => step.requiresVerification)).toBe(true);
  });

  it("uses local hints before provider-agnostic recipe teaching", () => {
    const steps = executableEscalationSteps(
      buildInteractionEscalationPlan(
        context({
          promotedRecipeAvailable: false,
          shadowRecipeAvailable: false,
          localSemanticHintEnabled: true,
          modelRecipeProposalEnabled: true,
        }),
      ),
    );

    expect(steps.map((step) => step.strategy)).toEqual([
      "NATIVE_CONTROL",
      "ARIA_PATTERN",
      "KEYBOARD_PATTERN",
      "STRUCTURAL_POPUP",
      "STATE_TRANSITION",
      "LOCAL_SEMANTIC_HINT",
      "MODEL_RECIPE_PROPOSAL",
      "VISUAL_ASSISTED_CONTROL",
    ]);
    expect(
      steps.find((step) => step.strategy === "MODEL_RECIPE_PROPOSAL")?.reason,
    ).toMatch(/configured model/);
  });

  it("keeps controlled visual fallback away from sensitive questions", () => {
    const plan = buildInteractionEscalationPlan(context({ sensitive: true }));
    const visual = plan.steps.find(
      (step) => step.strategy === "VISUAL_ASSISTED_CONTROL",
    );

    expect(visual).toMatchObject({ allowed: false, maxAttempts: 0 });
  });

  it("keeps local and model teaching away from sensitive questions", () => {
    const plan = buildInteractionEscalationPlan(
      context({
        sensitive: true,
        localSemanticHintEnabled: true,
        modelRecipeProposalEnabled: true,
      }),
    );
    const local = plan.steps.find(
      (step) => step.strategy === "LOCAL_SEMANTIC_HINT",
    );
    const model = plan.steps.find(
      (step) => step.strategy === "MODEL_RECIPE_PROPOSAL",
    );

    expect(local).toMatchObject({ allowed: false, maxAttempts: 0 });
    expect(model).toMatchObject({ allowed: false, maxAttempts: 0 });
  });

  it("keeps visual fallback away from irreversible actions", () => {
    const plan = buildInteractionEscalationPlan(context({ reversible: false }));
    const visual = plan.steps.find(
      (step) => step.strategy === "VISUAL_ASSISTED_CONTROL",
    );

    expect(visual?.allowed).toBe(false);
  });

  it("blocks the entire ladder at authentication boundaries", () => {
    const plan = buildInteractionEscalationPlan(
      context({
        authenticationBoundary: true,
        localSemanticHintEnabled: true,
        modelRecipeProposalEnabled: true,
      }),
    );

    expect(plan.blocked).toBe(true);
    expect(plan.blockReason).toMatch(/owner-controlled/);
    expect(executableEscalationSteps(plan)).toEqual([]);
  });

  it("blocks the entire ladder at final submission", () => {
    const plan = buildInteractionEscalationPlan(context({ finalSubmit: true }));

    expect(plan.blocked).toBe(true);
    expect(plan.blockReason).toMatch(/Final employer submission/);
  });

  it("skips unavailable recipe, keyboard, and popup paths", () => {
    const steps = executableEscalationSteps(
      buildInteractionEscalationPlan(
        context({
          promotedRecipeAvailable: false,
          shadowRecipeAvailable: false,
          keyboardOperable: false,
          popupExpected: false,
        }),
      ),
    );

    expect(steps.map((step) => step.strategy)).toEqual([
      "NATIVE_CONTROL",
      "ARIA_PATTERN",
      "STATE_TRANSITION",
      "VISUAL_ASSISTED_CONTROL",
    ]);
  });
});
