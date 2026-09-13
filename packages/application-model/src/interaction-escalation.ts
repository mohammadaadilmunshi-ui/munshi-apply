import type { ControlKind, SemanticType } from "@munshi-apply/contracts";

export type InteractionEscalationStrategy =
  | "PROMOTED_RECIPE"
  | "NATIVE_CONTROL"
  | "ARIA_PATTERN"
  | "KEYBOARD_PATTERN"
  | "STRUCTURAL_POPUP"
  | "STATE_TRANSITION"
  | "SHADOW_RECIPE"
  | "LOCAL_SEMANTIC_HINT"
  | "MODEL_RECIPE_PROPOSAL"
  | "VISUAL_ASSISTED_CONTROL";

export type InteractionEscalationContext = {
  kind: ControlKind;
  semanticType: SemanticType | null;
  sensitive: boolean;
  reversible: boolean;
  authenticationBoundary: boolean;
  finalSubmit: boolean;
  frameReachable: boolean;
  promotedRecipeAvailable: boolean;
  shadowRecipeAvailable: boolean;
  popupExpected: boolean;
  popupOwned: boolean;
  keyboardOperable: boolean;
  visualFallbackEnabled: boolean;
  /** Cheap/local classification may suggest mechanics, never candidate facts. */
  localSemanticHintEnabled?: boolean;
  /** Any approved model may propose value-free mechanics after deterministic failure. */
  modelRecipeProposalEnabled?: boolean;
};

export type InteractionEscalationStep = {
  strategy: InteractionEscalationStrategy;
  allowed: boolean;
  requiresVerification: true;
  maxAttempts: number;
  reason: string;
};

export type InteractionEscalationPlan = {
  blocked: boolean;
  blockReason: string | null;
  steps: InteractionEscalationStep[];
};

function denied(
  strategy: InteractionEscalationStrategy,
  reason: string,
): InteractionEscalationStep {
  return {
    strategy,
    allowed: false,
    requiresVerification: true,
    maxAttempts: 0,
    reason,
  };
}

function allowed(
  strategy: InteractionEscalationStrategy,
  reason: string,
  maxAttempts = 1,
): InteractionEscalationStep {
  return {
    strategy,
    allowed: true,
    requiresVerification: true,
    maxAttempts,
    reason,
  };
}

function hardBoundaryReason(
  context: InteractionEscalationContext,
): string | null {
  if (context.authenticationBoundary) {
    return "Authentication, MFA, OTP, identity verification, and equivalent security checkpoints remain owner-controlled";
  }
  if (context.finalSubmit) {
    return "Final employer submission remains owner-controlled";
  }
  if (!context.frameReachable) {
    return "The target frame is not safely reachable by the extension runtime";
  }
  return null;
}

/**
 * Deterministic-first escalation for reversible employer-form interaction.
 *
 * Paid/browser AI is a teacher of mechanics, not the default executor. Promoted
 * recipes and deterministic DOM/ARIA strategies run first. A local semantic hint
 * may classify a novel component. Only after those fail may an approved model
 * (Anthropic, OpenAI, Gemini, local, or another configured provider) propose a
 * bounded value-free recipe. Any learned recipe still requires verified SHADOW
 * successes before promotion.
 */
export function buildInteractionEscalationPlan(
  context: InteractionEscalationContext,
): InteractionEscalationPlan {
  const blockReason = hardBoundaryReason(context);
  if (blockReason) {
    return { blocked: true, blockReason, steps: [] };
  }

  const steps: InteractionEscalationStep[] = [];

  steps.push(
    context.promotedRecipeAvailable
      ? allowed(
          "PROMOTED_RECIPE",
          "A verified promoted interaction recipe is available for this component",
        )
      : denied(
          "PROMOTED_RECIPE",
          "No verified promoted interaction recipe is available",
        ),
  );

  steps.push(
    allowed(
      "NATIVE_CONTROL",
      `Try the ordinary ${context.kind.toLowerCase()} interaction path first`,
    ),
  );
  steps.push(
    allowed(
      "ARIA_PATTERN",
      "Use ARIA ownership, expanded state, selected state, and option semantics when ordinary control interaction does not verify",
    ),
  );

  steps.push(
    context.keyboardOperable
      ? allowed(
          "KEYBOARD_PATTERN",
          "Use bounded keyboard interaction when the component exposes a keyboard-operable pattern",
          2,
        )
      : denied(
          "KEYBOARD_PATTERN",
          "No safe keyboard-operable pattern was observed",
        ),
  );

  steps.push(
    context.popupExpected
      ? allowed(
          "STRUCTURAL_POPUP",
          context.popupOwned
            ? "Use the observed owned popup or portal as the interaction surface"
            : "Attempt bounded popup ownership recovery before selecting an option",
          2,
        )
      : denied(
          "STRUCTURAL_POPUP",
          "The control does not advertise or exhibit a popup interaction",
        ),
  );

  steps.push(
    allowed(
      "STATE_TRANSITION",
      "Drive the smallest reversible action sequence that produces a verified component state transition",
      2,
    ),
  );

  steps.push(
    context.shadowRecipeAvailable
      ? allowed(
          "SHADOW_RECIPE",
          "A compatible SHADOW recipe may be tested without promotion after ordinary strategies fail",
        )
      : denied("SHADOW_RECIPE", "No compatible SHADOW recipe is available"),
  );

  const localHintAllowed =
    Boolean(context.localSemanticHintEnabled) &&
    context.reversible &&
    !context.sensitive;
  steps.push(
    localHintAllowed
      ? allowed(
          "LOCAL_SEMANTIC_HINT",
          "Use a local/cheap classifier only to identify component mechanics; Candidate Truth remains authoritative for values",
        )
      : denied(
          "LOCAL_SEMANTIC_HINT",
          context.sensitive
            ? "Local semantic hint is disabled for sensitive questions"
            : !context.reversible
              ? "Local semantic hint is disabled for irreversible actions"
              : "Local semantic hint is not enabled",
        ),
  );

  const modelTeachingAllowed =
    Boolean(context.modelRecipeProposalEnabled) &&
    context.reversible &&
    !context.sensitive;
  steps.push(
    modelTeachingAllowed
      ? allowed(
          "MODEL_RECIPE_PROPOSAL",
          "Send compressed semantic control state to the configured model for a value-free mechanics proposal; verify in SHADOW before promotion",
        )
      : denied(
          "MODEL_RECIPE_PROPOSAL",
          context.sensitive
            ? "Model recipe teaching is disabled for sensitive questions"
            : !context.reversible
              ? "Model recipe teaching is disabled for irreversible actions"
              : "Model recipe teaching is not enabled",
        ),
  );

  const visualAllowed =
    context.visualFallbackEnabled && context.reversible && !context.sensitive;
  steps.push(
    visualAllowed
      ? allowed(
          "VISUAL_ASSISTED_CONTROL",
          "Use controlled cropped-component visual localization only for reversible, non-sensitive form interaction and verify the resulting DOM/application state",
        )
      : denied(
          "VISUAL_ASSISTED_CONTROL",
          context.sensitive
            ? "Visual fallback is disabled for sensitive questions"
            : !context.reversible
              ? "Visual fallback is disabled for irreversible actions"
              : "Visual fallback is not enabled",
        ),
  );

  return { blocked: false, blockReason: null, steps };
}

export function executableEscalationSteps(
  plan: InteractionEscalationPlan,
): InteractionEscalationStep[] {
  if (plan.blocked) return [];
  return plan.steps.filter((step) => step.allowed && step.maxAttempts > 0);
}
