import { describe, expect, it } from "vitest";
import {
  componentFingerprint,
  componentFingerprintCandidates,
  componentFingerprintV2,
  evaluateRecipePromotion,
  recipePerformance,
  shouldRollbackRecipe,
  type InteractionRecipe,
  type RecipeAttempt,
} from "./learning";

const recipe: InteractionRecipe = {
  recipeId: "recipe-1",
  componentFingerprint: "cfp-test",
  semanticType: "COUNTRY",
  siteOrigin: "https://example.test",
  actions: [
    { type: "FOCUS" },
    { type: "TYPE", valueSource: "ANSWER" },
    { type: "SELECT_EXACT_OPTION" },
  ],
  version: 1,
  state: "SHADOW",
  createdAt: "2026-08-14T18:00:00.000Z",
};

function attempt(
  index: number,
  success: boolean,
  verified = true,
): RecipeAttempt {
  return {
    attemptId: `attempt-${index}`,
    recipeId: recipe.recipeId,
    occurredAt: `2026-08-14T18:00:${String(index).padStart(2, "0")}.000Z`,
    success,
    verified,
    failureReason: success ? null : "value did not verify",
  };
}

describe("componentFingerprint", () => {
  it("is stable for the same structural component signals", () => {
    const input = {
      kind: "COMBOBOX" as const,
      tagName: "INPUT",
      role: "combobox",
      inputType: "text",
      optionCount: 5,
      ariaAutocomplete: "list",
      hasPopup: "listbox",
    };
    expect(componentFingerprint(input)).toBe(componentFingerprint(input));
  });

  it("changes when a material component capability changes", () => {
    const first = componentFingerprint({
      kind: "COMBOBOX",
      tagName: "input",
      role: "combobox",
      inputType: "text",
      optionCount: 5,
      ariaAutocomplete: "list",
      hasPopup: "listbox",
    });
    const second = componentFingerprint({
      kind: "COMBOBOX",
      tagName: "input",
      role: "combobox",
      inputType: "text",
      optionCount: 0,
      ariaAutocomplete: "none",
      hasPopup: "listbox",
    });
    expect(second).not.toBe(first);
  });

  it("adds shadow, frame, portal, virtualization, and framework structure in v2", () => {
    const base = {
      kind: "COMBOBOX" as const,
      tagName: "input",
      role: "combobox",
      inputType: "text",
      optionCount: 50,
      ariaAutocomplete: "list",
      hasPopup: "listbox",
      multiple: false,
      contentEditable: false,
      shadowDepth: 1,
      frameDepth: 0,
      portaledPopup: true,
      virtualizedOptions: true,
      popupOwnerKind: "ARIA_CONTROLS" as const,
      frameworkHint: "REACT" as const,
    };

    expect(componentFingerprintV2(base)).not.toBe(
      componentFingerprintV2({ ...base, virtualizedOptions: false }),
    );
    expect(componentFingerprintV2(base)).not.toBe(
      componentFingerprintV2({ ...base, shadowDepth: 2 }),
    );
  });

  it("returns v2 then legacy candidates for recipe migration compatibility", () => {
    const input = {
      kind: "COMBOBOX" as const,
      tagName: "input",
      role: "combobox",
      inputType: "text",
      optionCount: 5,
      ariaAutocomplete: "list",
      hasPopup: "listbox",
      frameworkHint: "REACT" as const,
    };
    const candidates = componentFingerprintCandidates(input);

    expect(candidates[0]).toMatch(/^cfp2-/);
    expect(candidates[1]).toBe(componentFingerprint(input));
  });
});

describe("verified recipe learning", () => {
  it("ignores unverified attempts when calculating performance", () => {
    const performance = recipePerformance(recipe.recipeId, [
      attempt(1, true),
      attempt(2, false, false),
    ]);
    expect(performance).toMatchObject({
      verifiedAttempts: 1,
      successes: 1,
      failures: 0,
      successRate: 1,
    });
  });

  it("promotes only after the verified threshold is met", () => {
    const attempts = [
      attempt(1, true),
      attempt(2, true),
      attempt(3, true),
      attempt(4, true),
      attempt(5, false),
    ];
    const result = evaluateRecipePromotion(recipe, attempts, {
      minimumVerifiedAttempts: 5,
      minimumSuccessRate: 0.8,
    });
    expect(result.eligible).toBe(true);
    expect(result.performance.successRate).toBe(0.8);
  });

  it("does not promote a recipe based on too little evidence", () => {
    const result = evaluateRecipePromotion(recipe, [attempt(1, true)], {
      minimumVerifiedAttempts: 5,
      minimumSuccessRate: 0.8,
    });
    expect(result.eligible).toBe(false);
  });

  it("rolls back a promoted recipe after configured consecutive verified failures", () => {
    const promoted = { ...recipe, state: "PROMOTED" as const };
    expect(
      shouldRollbackRecipe(
        promoted,
        [
          attempt(1, true),
          attempt(2, false),
          attempt(3, false),
          attempt(4, false),
        ],
        3,
      ),
    ).toBe(true);
  });
});
