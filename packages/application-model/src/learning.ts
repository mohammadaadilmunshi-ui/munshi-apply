import type { ControlKind, SemanticType } from "@munshi-apply/contracts";

export type ComponentFingerprintInput = {
  kind: ControlKind;
  tagName: string;
  role: string | null;
  inputType: string | null;
  optionCount: number;
  ariaAutocomplete: string | null;
  hasPopup: string | null;
};

export type PopupOwnerKind =
  "ARIA_CONTROLS" | "ARIA_OWNS" | "DOM_DESCENDANT" | "PORTAL" | "UNKNOWN";

export type ComponentFrameworkHint =
  "NATIVE" | "REACT" | "ANGULAR" | "VUE" | "CUSTOM_ELEMENT" | "UNKNOWN";

export type ComponentFingerprintV2Input = ComponentFingerprintInput & {
  multiple?: boolean;
  contentEditable?: boolean;
  shadowDepth?: number;
  frameDepth?: number;
  portaledPopup?: boolean;
  virtualizedOptions?: boolean;
  popupOwnerKind?: PopupOwnerKind;
  frameworkHint?: ComponentFrameworkHint;
};

export type RecipeAction =
  | { type: "FOCUS" }
  | { type: "CLICK" }
  | { type: "TYPE"; valueSource: "ANSWER" }
  | {
      type: "KEY";
      key: "ArrowDown" | "ArrowUp" | "Enter" | "Tab" | "Escape";
    }
  | { type: "SELECT_EXACT_OPTION" }
  | { type: "WAIT_FOR_STATE"; state: "OPTIONS_VISIBLE" | "VALUE_COMMITTED" };

export type InteractionRecipe = {
  recipeId: string;
  componentFingerprint: string;
  semanticType: SemanticType | null;
  siteOrigin: string | null;
  actions: readonly RecipeAction[];
  version: number;
  state: "SHADOW" | "PROMOTED" | "ROLLED_BACK";
  createdAt: string;
};

export type RecipeAttempt = {
  attemptId: string;
  recipeId: string;
  occurredAt: string;
  success: boolean;
  verified: boolean;
  failureReason: string | null;
};

export type RecipePerformance = {
  verifiedAttempts: number;
  successes: number;
  failures: number;
  successRate: number;
};

export type PromotionPolicy = {
  minimumVerifiedAttempts: number;
  minimumSuccessRate: number;
};

function stableHash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function normalize(value: string | null): string {
  return (value ?? "").replace(/\s+/g, " ").trim().toLowerCase();
}

function validateDepth(value: number | undefined, label: string): number {
  const resolved = value ?? 0;
  if (!Number.isSafeInteger(resolved) || resolved < 0 || resolved > 32) {
    throw new Error(`${label} must be an integer between 0 and 32`);
  }
  return resolved;
}

export function componentFingerprint(input: ComponentFingerprintInput): string {
  if (!Number.isSafeInteger(input.optionCount) || input.optionCount < 0) {
    throw new Error("optionCount must be a non-negative integer");
  }
  const signature = [
    input.kind,
    input.tagName.toLowerCase(),
    normalize(input.role),
    normalize(input.inputType),
    String(input.optionCount),
    normalize(input.ariaAutocomplete),
    normalize(input.hasPopup),
  ].join("|");
  return `cfp-${stableHash(signature)}`;
}

/**
 * Richer structural fingerprint used for new learning without invalidating
 * existing v1 recipes. It intentionally excludes element ids, labels, entered
 * values, and other owner/job text so recipes describe component mechanics.
 */
export function componentFingerprintV2(
  input: ComponentFingerprintV2Input,
): string {
  if (!Number.isSafeInteger(input.optionCount) || input.optionCount < 0) {
    throw new Error("optionCount must be a non-negative integer");
  }
  const signature = [
    "v2",
    input.kind,
    input.tagName.toLowerCase(),
    normalize(input.role),
    normalize(input.inputType),
    String(input.optionCount),
    normalize(input.ariaAutocomplete),
    normalize(input.hasPopup),
    String(input.multiple === true),
    String(input.contentEditable === true),
    String(validateDepth(input.shadowDepth, "shadowDepth")),
    String(validateDepth(input.frameDepth, "frameDepth")),
    String(input.portaledPopup === true),
    String(input.virtualizedOptions === true),
    input.popupOwnerKind ?? "UNKNOWN",
    input.frameworkHint ?? "UNKNOWN",
  ].join("|");
  return `cfp2-${stableHash(signature)}`;
}

/**
 * New runtimes query the richer fingerprint first and fall back to the legacy
 * fingerprint so previously promoted recipes remain usable during migration.
 */
export function componentFingerprintCandidates(
  input: ComponentFingerprintV2Input,
): readonly [string, string] {
  return [componentFingerprintV2(input), componentFingerprint(input)];
}

export function validateRecipe(recipe: InteractionRecipe): void {
  if (!recipe.recipeId.trim() || !recipe.componentFingerprint.trim()) {
    throw new Error("Recipe identifiers are required");
  }
  if (!Number.isSafeInteger(recipe.version) || recipe.version < 1) {
    throw new Error("Recipe version must be a positive integer");
  }
  if (recipe.actions.length === 0) {
    throw new Error("Recipe must contain at least one interaction action");
  }
  for (const action of recipe.actions) {
    if (!("type" in action)) throw new Error("Recipe action is invalid");
  }
}

export function recipePerformance(
  recipeId: string,
  attempts: readonly RecipeAttempt[],
): RecipePerformance {
  const verified = attempts.filter(
    (attempt) => attempt.recipeId === recipeId && attempt.verified,
  );
  const successes = verified.filter((attempt) => attempt.success).length;
  const failures = verified.length - successes;
  return {
    verifiedAttempts: verified.length,
    successes,
    failures,
    successRate:
      verified.length === 0
        ? 0
        : Number((successes / verified.length).toFixed(6)),
  };
}

export function evaluateRecipePromotion(
  recipe: InteractionRecipe,
  attempts: readonly RecipeAttempt[],
  policy: PromotionPolicy,
): { eligible: boolean; reason: string; performance: RecipePerformance } {
  validateRecipe(recipe);
  if (
    !Number.isSafeInteger(policy.minimumVerifiedAttempts) ||
    policy.minimumVerifiedAttempts < 1
  ) {
    throw new Error("minimumVerifiedAttempts must be a positive integer");
  }
  if (
    !Number.isFinite(policy.minimumSuccessRate) ||
    policy.minimumSuccessRate < 0 ||
    policy.minimumSuccessRate > 1
  ) {
    throw new Error("minimumSuccessRate must be between 0 and 1");
  }
  const performance = recipePerformance(recipe.recipeId, attempts);
  if (recipe.state !== "SHADOW") {
    return {
      eligible: false,
      reason: "Only shadow recipes can be promoted",
      performance,
    };
  }
  if (performance.verifiedAttempts < policy.minimumVerifiedAttempts) {
    return {
      eligible: false,
      reason: "Recipe does not have enough verified attempts",
      performance,
    };
  }
  if (performance.successRate < policy.minimumSuccessRate) {
    return {
      eligible: false,
      reason: "Recipe success rate is below the promotion threshold",
      performance,
    };
  }
  return {
    eligible: true,
    reason: "Recipe meets the verified promotion threshold",
    performance,
  };
}

export function shouldRollbackRecipe(
  recipe: InteractionRecipe,
  attempts: readonly RecipeAttempt[],
  consecutiveVerifiedFailures: number,
): boolean {
  validateRecipe(recipe);
  if (
    !Number.isSafeInteger(consecutiveVerifiedFailures) ||
    consecutiveVerifiedFailures < 1
  ) {
    throw new Error("consecutiveVerifiedFailures must be a positive integer");
  }
  if (recipe.state !== "PROMOTED") return false;
  const verified = attempts
    .filter(
      (attempt) => attempt.recipeId === recipe.recipeId && attempt.verified,
    )
    .sort((left, right) => right.occurredAt.localeCompare(left.occurredAt));
  if (verified.length < consecutiveVerifiedFailures) return false;
  return verified
    .slice(0, consecutiveVerifiedFailures)
    .every((attempt) => !attempt.success);
}
