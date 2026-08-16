from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:100]!r}")
    write(path, content.replace(old, new, 1))


replace_once(
    "apps/extension/public/manifest.json",
    '"version": "0.2.3"',
    '"version": "0.2.4"',
)

replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    """export type AutoPilotLaunchPlan = {
  preflight: PreflightGateSummary;
  fillInstructions: FillInstruction[];
  manualControls: Control[];
  optionalUnansweredCount: number;
};""",
    """export type AutoPilotLaunchPlan = {
  preflight: PreflightGateSummary;
  fillInstructions: FillInstruction[];
  manualControls: Control[];
  optionalUnansweredCount: number;
  requiredReviewCount: number;
  optionalReviewCount: number;
};""",
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    """  let reviewCount = 0;
  let unresolvedCount = 0;
  let optionalUnansweredCount = 0;""",
    """  let requiredReviewCount = 0;
  let optionalReviewCount = 0;
  let unresolvedCount = 0;
  let optionalUnansweredCount = 0;""",
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    """    if (!answer?.approved) {
      reviewCount += 1;
      continue;
    }""",
    """    if (!answer?.approved) {
      if (control.required) requiredReviewCount += 1;
      else optionalReviewCount += 1;
      continue;
    }""",
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    """      : reviewCount > 0 || unresolvedCount > 0 || manualCount > 0
        ? \"REVIEW\"
        : \"READY\";""",
    """      : requiredReviewCount > 0 || unresolvedCount > 0 || manualCount > 0
        ? \"REVIEW\"
        : \"READY\";""",
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    """    reviewCount: reviewCount + manualCount,""",
    """    reviewCount: requiredReviewCount + optionalReviewCount + manualCount,""",
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    """    manualControls: [...manual.values()],
    optionalUnansweredCount,
  };""",
    """    manualControls: [...manual.values()],
    optionalUnansweredCount,
    requiredReviewCount,
    optionalReviewCount,
  };""",
)

replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.test.ts",
    """  it(\"carries an approved AI draft identity into the AutoPilot fill instruction\", () => {""",
    """  it(\"does not block page progress for an optional answer that has not been approved\", () => {
    const current = page();
    current.controls = [{ ...current.controls[0]!, required: false }];
    current.questions = [current.questions[0]!];
    const result = buildAutoPilotLaunchPlan(current, {
      \"q-name\": { value: \"Optional note\", approved: false, sensitive: false },
    });
    expect(result.preflight.state).toBe(\"READY\");
    expect(result.preflight.canAct).toBe(true);
    expect(result.requiredReviewCount).toBe(0);
    expect(result.optionalReviewCount).toBe(1);
  });

  it(\"still blocks navigation for a required answer that has not been approved\", () => {
    const current = page();
    current.controls = [current.controls[0]!];
    current.questions = [current.questions[0]!];
    const result = buildAutoPilotLaunchPlan(current, {
      \"q-name\": { value: \"Required value\", approved: false, sensitive: false },
    });
    expect(result.preflight.state).toBe(\"REVIEW\");
    expect(result.preflight.canAct).toBe(false);
    expect(result.requiredReviewCount).toBe(1);
    expect(result.optionalReviewCount).toBe(0);
  });

  it(\"carries an approved AI draft identity into the AutoPilot fill instruction\", () => {""",
)

replace_once(
    "packages/application-model/src/autopilot-session.ts",
    """  if (observation.validationErrorCount > 0) {
    return {
      ...session,
      status: \"PAUSED_REVIEW\",
      securityCheckpoint: null,
      pauseReason: \"Current page contains validation errors\",
      lastApplicationState: observation.state,
      lastPageId: observation.pageId,
      lastPageFingerprint: observation.pageFingerprint,
      updatedAt: at,
    };
  }
""",
    """  // Application forms commonly expose required-field validation while they are
  // still incomplete. Do not treat those messages as a session-level stop before
  // AutoPilot has had a chance to fill the approved fields. The step planner checks
  // validation again after safe fill work is exhausted and before navigation.
""",
)
replace_once(
    "packages/application-model/src/autopilot-session.test.ts",
    """  it(\"pauses on security, validation, final submission, and wrong application\", () => {""",
    """  it(\"pauses on security/final boundaries but lets incomplete-form validation reach the step planner\", () => {""",
)
replace_once(
    "packages/application-model/src/autopilot-session.test.ts",
    """    expect(
      reduceAutoPilotSession(session, {
        type: \"START\",
        observation: { ...observation, validationErrorCount: 1 },
        at: \"2026-08-14T21:00:01.000Z\",
      }).status,
    ).toBe(\"PAUSED_REVIEW\");""",
    """    expect(
      reduceAutoPilotSession(session, {
        type: \"START\",
        observation: { ...observation, validationErrorCount: 1 },
        at: \"2026-08-14T21:00:01.000Z\",
      }).status,
    ).toBe(\"RUNNING\");""",
)

replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    """    if (result.status !== \"NAVIGATED\") {
      return this.fail(
        current,
        `Navigation was not verified for dispatch: ${result.reason}`,
      );
    }""",
    """    if (result.status !== \"NAVIGATED\") {
      const recoverable = parseAutoPilotRuntimeState({
        ...current,
        actionDeadlineAt: null,
        navigationDispatchAttempted: false,
      });
      return this.persistPause(recoverable, observationFor(recoverable, page), {
        type: \"REVIEW\",
        reason: `MUNSHI could not complete this forward navigation automatically: ${result.reason}. Click the employer's forward control once, then Resume AutoPilot. If the control itself is unusual, use Teach MUNSHI first.`,
      });
    }""",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    """        if (!verification.success) {
          return this.fail(
            armed,
            `Fill verification failed: ${verification.reason}`,
          );
        }

        const waiting = parseAutoPilotRuntimeState({""",
    """        if (!verification.success) {
          const failedResult =
            results.find(
              (result) => result.controlId === fillInstruction.controlId,
            ) ?? null;
          const recoverable = parseAutoPilotRuntimeState({
            ...armed,
            dispatchingFillControlId: null,
            pendingDraftUsageId: null,
            actionDeadlineAt: null,
            lastFillResult: failedResult,
          });
          return this.persistPause(
            recoverable,
            observationFor(recoverable, page),
            {
              type: \"REVIEW\",
              reason: `MUNSHI could not verify this control: ${verification.reason}. You can correct it manually or use Teach MUNSHI, then Resume AutoPilot without losing the application.`,
            },
          );
        }

        const waiting = parseAutoPilotRuntimeState({""",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    """    if (runtime.dispatchingFillControlId) {
      runtime = await this.fail(
        runtime,
        \"A field fill was interrupted before verification; owner review is required\",
      );
      return this.statusFromRuntime(runtime);
    }""",
    """    if (runtime.dispatchingFillControlId) {
      const interruptedControlId = runtime.dispatchingFillControlId;
      const recoverable = parseAutoPilotRuntimeState({
        ...runtime,
        dispatchingFillControlId: null,
        pendingDraftUsageId: null,
        actionDeadlineAt: null,
      });
      runtime = await this.persistPause(
        recoverable,
        observationFor(recoverable, page),
        {
          type: \"REVIEW\",
          reason: `The browser interrupted ${interruptedControlId} before verification. Check that field once, then Resume AutoPilot; progress and the durable checkpoint were preserved.`,
        },
      );
      return this.statusFromRuntime(runtime);
    }""",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    """      runtime = await this.fail(
        runtime,
        \"AutoPilot action timed out before verification\",
      );
      return this.statusFromRuntime(runtime);""",
    """      const page = await this.dependencies.getPage(runtime.tabId);
      if (page) {
        runtime = await this.persistPause(
          parseAutoPilotRuntimeState({
            ...runtime,
            dispatchingFillControlId: null,
            actionDeadlineAt: null,
            navigationDispatchAttempted: false,
          }),
          observationFor(runtime, page),
          {
            type: \"REVIEW\",
            reason:
              \"The employer page did not reach a verifiable state before the timeout. Check the active control, use Teach MUNSHI if needed, then Resume AutoPilot.\",
          },
        );
      } else {
        runtime = await this.fail(
          runtime,
          \"AutoPilot timed out and the application page is unavailable\",
        );
      }
      return this.statusFromRuntime(runtime);""",
)

write(
    "apps/extension/src/content/teach.ts",
    r'''import type { RecipeAction } from "@munshi-apply/application-model";
import { isAriaMultiSelectControl } from "./advanced-controls";
import { isPopupChoiceControl } from "./adaptive";
import { resolveControlElement } from "./scanner";

export type TeachInteractionStart = {
  sessionId: string;
  controlId: string;
  label: string;
  componentFingerprint: string;
  startedAt: string;
};

export type TeachInteractionCapture = {
  sessionId: string;
  controlId: string;
  componentFingerprint: string;
  changed: boolean;
  reusable: boolean;
  actions: RecipeAction[];
  eventTypes: string[];
  startedAt: string;
  finishedAt: string;
};

type ActiveTeachSession = TeachInteractionStart & {
  element: HTMLElement;
  beforeMarker: string;
  eventTypes: Set<string>;
  abortController: AbortController;
};

let active: ActiveTeachSession | null = null;

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function marker(element: HTMLElement): string {
  const input = element instanceof HTMLInputElement ? element : null;
  const select = element instanceof HTMLSelectElement ? element : null;
  const textarea = element instanceof HTMLTextAreaElement ? element : null;
  return JSON.stringify({
    checked: input?.checked ?? element.getAttribute("aria-checked"),
    selected: element.getAttribute("aria-selected"),
    expanded: element.getAttribute("aria-expanded"),
    value: input?.value ?? select?.value ?? textarea?.value ?? element.textContent ?? "",
  });
}

function teachable(element: HTMLElement): boolean {
  if (element instanceof HTMLInputElement) {
    return !["file", "password", "hidden", "submit", "button", "reset"].includes(
      element.type,
    );
  }
  if (element instanceof HTMLButtonElement) return false;
  return true;
}

function inferredActions(element: HTMLElement, eventTypes: Set<string>): RecipeAction[] {
  if (isAriaMultiSelectControl(element)) {
    return [
      { type: "FOCUS" },
      { type: "CLICK" },
      { type: "WAIT_FOR_STATE", state: "OPTIONS_VISIBLE" },
      { type: "SELECT_EXACT_OPTION" },
      { type: "WAIT_FOR_STATE", state: "VALUE_COMMITTED" },
    ];
  }
  if (isPopupChoiceControl(element)) {
    const actions: RecipeAction[] = [
      { type: "FOCUS" },
      { type: "CLICK" },
      { type: "WAIT_FOR_STATE", state: "OPTIONS_VISIBLE" },
    ];
    if (
      element instanceof HTMLInputElement &&
      (eventTypes.has("input") || eventTypes.has("change"))
    ) {
      actions.push({ type: "TYPE", valueSource: "ANSWER" });
    }
    actions.push(
      { type: "SELECT_EXACT_OPTION" },
      { type: "WAIT_FOR_STATE", state: "VALUE_COMMITTED" },
    );
    return actions;
  }
  if (
    element instanceof HTMLSelectElement ||
    element.getAttribute("role") === "listbox"
  ) {
    return [
      { type: "FOCUS" },
      { type: "SELECT_EXACT_OPTION" },
      { type: "WAIT_FOR_STATE", state: "VALUE_COMMITTED" },
    ];
  }
  if (
    (element instanceof HTMLInputElement &&
      ["radio", "checkbox"].includes(element.type)) ||
    ["radio", "checkbox", "switch"].includes(element.getAttribute("role") ?? "")
  ) {
    return [
      { type: "FOCUS" },
      { type: "CLICK" },
      { type: "WAIT_FOR_STATE", state: "VALUE_COMMITTED" },
    ];
  }
  if (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element.isContentEditable
  ) {
    return [
      { type: "FOCUS" },
      { type: "TYPE", valueSource: "ANSWER" },
      { type: "WAIT_FOR_STATE", state: "VALUE_COMMITTED" },
    ];
  }
  return [];
}

function dispose(): void {
  active?.abortController.abort();
  active = null;
}

export function beginTeachInteraction(
  sessionId: string,
  controlId: string,
): TeachInteractionStart {
  dispose();
  const resolved = resolveControlElement(controlId);
  const element = resolved?.element;
  if (!(element instanceof HTMLElement) || !teachable(element)) {
    throw new Error(
      "This employer control is not eligible for Teach MUNSHI. File/security/final actions stay owner-operated.",
    );
  }
  const componentFingerprint = resolved?.control.componentFingerprint ?? "";
  if (!componentFingerprint) {
    throw new Error("This control does not have a reusable component fingerprint yet");
  }
  const abortController = new AbortController();
  const eventTypes = new Set<string>();
  const options = { capture: true, signal: abortController.signal } as const;
  for (const eventName of ["focus", "click", "input", "change", "keydown", "blur"]) {
    document.addEventListener(
      eventName,
      (event) => {
        if (eventName === "keydown" && event instanceof KeyboardEvent) {
          if (!["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(event.key)) {
            return;
          }
          eventTypes.add(`key:${event.key}`);
          return;
        }
        eventTypes.add(eventName);
      },
      options,
    );
  }
  const startedAt = new Date().toISOString();
  active = {
    sessionId,
    controlId,
    label: compact(
      resolved?.control.label || resolved?.control.ariaLabel || resolved?.control.name,
    ),
    componentFingerprint,
    startedAt,
    element,
    beforeMarker: marker(element),
    eventTypes,
    abortController,
  };
  element.scrollIntoView?.({ block: "center", inline: "nearest" });
  return {
    sessionId,
    controlId,
    label: active.label,
    componentFingerprint,
    startedAt,
  };
}

export function finishTeachInteraction(sessionId: string): TeachInteractionCapture {
  if (!active || active.sessionId !== sessionId) {
    throw new Error("Teach MUNSHI session is no longer active in this frame");
  }
  const current = active;
  const actions = inferredActions(current.element, current.eventTypes);
  const changed =
    current.beforeMarker !== marker(current.element) ||
    current.eventTypes.has("input") ||
    current.eventTypes.has("change") ||
    current.eventTypes.has("click");
  const result: TeachInteractionCapture = {
    sessionId: current.sessionId,
    controlId: current.controlId,
    componentFingerprint: current.componentFingerprint,
    changed,
    reusable: changed && actions.length > 0,
    actions,
    eventTypes: [...current.eventTypes],
    startedAt: current.startedAt,
    finishedAt: new Date().toISOString(),
  };
  dispose();
  return result;
}

export function cancelTeachInteraction(sessionId: string): { cancelled: boolean } {
  if (!active || active.sessionId !== sessionId) return { cancelled: false };
  dispose();
  return { cancelled: true };
}
''',
)

write(
    "apps/extension/src/content/teach.test.ts",
    r'''// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { scanDocument } from "./scanner";
import {
  beginTeachInteraction,
  cancelTeachInteraction,
  finishTeachInteraction,
} from "./teach";

const visibleRectangle: DOMRect = {
  bottom: 40,
  height: 30,
  left: 10,
  right: 210,
  top: 10,
  width: 200,
  x: 10,
  y: 10,
  toJSON: () => ({}),
};

describe("Teach MUNSHI capture", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("captures a demonstration as value-free reusable actions", () => {
    document.body.innerHTML = `
      <label for="country">Country</label>
      <input id="country" role="combobox" aria-expanded="false" aria-controls="countries" />
      <div id="countries" role="listbox">
        <div role="option">United States</div>
      </div>
    `;
    const page = scanDocument();
    const control = page.controls.find((item) => item.label === "Country")!;
    const input = document.getElementById("country") as HTMLInputElement;
    const started = beginTeachInteraction("teach-1", control.controlId);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.reusable).toBe(true);
    expect(learned.actions.map((action) => action.type)).toContain(
      "SELECT_EXACT_OPTION",
    );
    expect(JSON.stringify(learned)).not.toContain("United States");
  });

  it("cancels without retaining a demonstration", () => {
    document.body.innerHTML = `<label for="name">Name</label><input id="name" />`;
    const control = scanDocument().controls[0]!;
    const started = beginTeachInteraction("teach-2", control.controlId);
    expect(cancelTeachInteraction(started.sessionId).cancelled).toBe(true);
    expect(() => finishTeachInteraction(started.sessionId)).toThrow(/no longer active/);
  });
});
''',
)

replace_once(
    "apps/extension/src/content/fill.ts",
    'import type { FillInstruction, FillResult } from "@munshi-apply/contracts";',
    'import type { RecipeAction } from "@munshi-apply/application-model";\nimport type { FillInstruction, FillResult } from "@munshi-apply/contracts";',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    """export type FillInteractionOptions = {
  optionTimeoutMs?: number;
  pollIntervalMs?: number;
  verificationTimeoutMs?: number;
  stabilityQuietMs?: number;
  stabilityTimeoutMs?: number;
};""",
    """export type FillInteractionOptions = {
  optionTimeoutMs?: number;
  pollIntervalMs?: number;
  verificationTimeoutMs?: number;
  stabilityQuietMs?: number;
  stabilityTimeoutMs?: number;
};

export type PreferredInteractionRecipe = {
  recipeId: string;
  strategy: \"TAUGHT_RECIPE\";
  actions: readonly RecipeAction[];
  state: \"SHADOW\" | \"PROMOTED\";
  version: number;
};""",
)
replace_once(
    "apps/extension/src/content/fill.ts",
    """function radioVerified(element: HTMLInputElement, value: string): boolean {
  const checked = radioCandidates(element).filter(
    (candidate) => candidate.checked,
  );
  return checked.length === 1 && radioMatches(checked[0]!, value);
}

async function fillElement(""",
    r'''function radioVerified(element: HTMLInputElement, value: string): boolean {
  const checked = radioCandidates(element).filter(
    (candidate) => candidate.checked,
  );
  return checked.length === 1 && radioMatches(checked[0]!, value);
}

function recipeValueCommitted(element: HTMLElement, value: string): boolean {
  const context = interactionContext(element);
  if (element instanceof HTMLSelectElement) {
    const selected = Array.from(element.selectedOptions).flatMap((option) => [
      option.value,
      option.text,
    ]);
    return selected.some((candidate) => optionEquivalent(candidate, value, context));
  }
  if (element instanceof HTMLInputElement) {
    if (element.type === "radio") return radioVerified(element, value);
    if (element.type === "checkbox") {
      const requested = normalized(value);
      const shouldCheck = ["true", "yes", "1", "checked"].includes(requested);
      return element.checked === shouldCheck;
    }
    return optionEquivalent(element.value, value, context) || element.value === value;
  }
  if (element instanceof HTMLTextAreaElement) return element.value === value;
  if (element.isContentEditable) return compactText(element.textContent) === compactText(value);
  const ariaChecked = element.getAttribute("aria-checked");
  if (ariaChecked !== null) {
    const requested = normalized(value);
    if (["true", "yes", "1", "checked"].includes(requested)) return ariaChecked === "true";
    if (["false", "no", "0", "unchecked"].includes(requested)) return ariaChecked === "false";
  }
  return optionEquivalent(element.textContent ?? "", value, context);
}

function typeRecipeValue(element: HTMLElement, value: string): boolean {
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    setNativeValue(element, value);
    dispatchInputEvent(element);
    return true;
  }
  if (element.isContentEditable) {
    element.textContent = value;
    dispatchInputEvent(element);
    return true;
  }
  return false;
}

function dispatchRecipeKey(element: HTMLElement, key: string): void {
  element.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, composed: true }));
  element.dispatchEvent(new KeyboardEvent("keyup", { key, bubbles: true, composed: true }));
}

async function executeInteractionRecipe(
  element: HTMLElement,
  value: string,
  recipe: PreferredInteractionRecipe,
  options: Required<FillInteractionOptions>,
): Promise<boolean> {
  if (recipe.actions.length === 0 || recipe.actions.length > 16) return false;
  for (const action of recipe.actions) {
    if (action.type === "FOCUS") {
      element.focus();
      continue;
    }
    if (action.type === "CLICK") {
      if (element instanceof HTMLInputElement && element.type === "radio") {
        if (!fillRadio(element, value)) return false;
        continue;
      }
      if (element instanceof HTMLInputElement && element.type === "checkbox") {
        if (!fillCheckbox(element, value)) return false;
        continue;
      }
      const ariaRadio = await fillAriaRadioControl(element, value, options);
      if (ariaRadio !== null) {
        if (!ariaRadio) return false;
        continue;
      }
      const ariaBoolean = await fillAriaBooleanControl(element, value, options);
      if (ariaBoolean !== null) {
        if (!ariaBoolean) return false;
        continue;
      }
      element.click();
      continue;
    }
    if (action.type === "TYPE") {
      if (!typeRecipeValue(element, value)) return false;
      continue;
    }
    if (action.type === "KEY") {
      dispatchRecipeKey(element, action.key);
      continue;
    }
    if (action.type === "SELECT_EXACT_OPTION") {
      if (element instanceof HTMLSelectElement) {
        const context = interactionContext(element);
        const option = uniqueOptionCandidate(
          value,
          Array.from(element.options)
            .filter((candidate) => !candidate.disabled)
            .map((candidate) => ({ item: candidate, values: [candidate.value, candidate.text] })),
          context,
        );
        if (!option) return false;
        element.value = option.value;
        dispatchValueEvents(element);
        continue;
      }
      const option = await waitForExactComboboxOption(
        element,
        value,
        options.optionTimeoutMs,
        options.pollIntervalMs,
      );
      if (!option) return false;
      option.click();
      element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      continue;
    }
    if (action.type === "WAIT_FOR_STATE" && action.state === "OPTIONS_VISIBLE") {
      if (element instanceof HTMLSelectElement) continue;
      const option = await waitForExactComboboxOption(
        element,
        value,
        options.optionTimeoutMs,
        options.pollIntervalMs,
      );
      if (!option) return false;
      continue;
    }
    if (action.type === "WAIT_FOR_STATE" && action.state === "VALUE_COMMITTED") {
      const committed = await waitForVerification(
        () => recipeValueCommitted(element, value),
        options.verificationTimeoutMs,
        options.pollIntervalMs,
      );
      if (!committed) return false;
      continue;
    }
    return false;
  }
  return waitForVerification(
    () => recipeValueCommitted(element, value),
    options.verificationTimeoutMs,
    options.pollIntervalMs,
  );
}

async function fillElement(''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    """export async function applyFillInstructions(
  instructions: FillInstruction[],
  interactionOptions: FillInteractionOptions = {},
): Promise<FillResult[]> {""",
    """export async function applyFillInstructions(
  instructions: FillInstruction[],
  interactionOptions: FillInteractionOptions = {},
  preferredRecipes: Record<string, PreferredInteractionRecipe> = {},
): Promise<FillResult[]> {""",
)
replace_once(
    "apps/extension/src/content/fill.ts",
    """    let filled = false;
    const strategy = strategyFor(element);
    try {
      filled = await fillElement(element, instruction.value, options);
    } catch {
      filled = false;
    }
    const stabilized = filled""",
    """    let filled = false;
    const fallbackStrategy = strategyFor(element);
    const recipe = preferredRecipes[instruction.controlId];
    let recipeAttempted = false;
    let recipeSucceeded = false;
    if (recipe) {
      recipeAttempted = true;
      try {
        recipeSucceeded = await executeInteractionRecipe(
          element as HTMLElement,
          instruction.value,
          recipe,
          options,
        );
      } catch {
        recipeSucceeded = false;
      }
      filled = recipeSucceeded;
    }
    if (!filled) {
      try {
        filled = await fillElement(element, instruction.value, options);
      } catch {
        filled = false;
      }
    }
    const stabilized = filled""",
)
replace_once(
    "apps/extension/src/content/fill.ts",
    """      strategy,
      verification: filled ? \"POST_ACTION_DOM_VERIFIED\" : \"FAILED_CLOSED\",
      rebound: resolved?.rebound ?? false,
      stabilized,
      componentFingerprint: resolved?.control.componentFingerprint,
    });""",
    """      strategy: recipeSucceeded ? recipe!.strategy : fallbackStrategy,
      verification: filled ? \"POST_ACTION_DOM_VERIFIED\" : \"FAILED_CLOSED\",
      rebound: resolved?.rebound ?? false,
      stabilized,
      componentFingerprint: resolved?.control.componentFingerprint,
      recipeId: recipe?.recipeId,
      recipeAttempted,
      recipeSucceeded: recipeAttempted ? recipeSucceeded : undefined,
    });""",
)

replace_once(
    "apps/extension/src/content/bootstrap.ts",
    'import { applyFillInstructions, assistFilePicker } from "./fill";',
    'import {\n  applyFillInstructions,\n  assistFilePicker,\n  type PreferredInteractionRecipe,\n} from "./fill";\nimport {\n  beginTeachInteraction,\n  cancelTeachInteraction,\n  finishTeachInteraction,\n} from "./teach";',
)
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    """    instructions?: FillInstruction[];
    controlId?: string;
  },""",
    """    instructions?: FillInstruction[];
    preferredRecipes?: Record<string, PreferredInteractionRecipe>;
    controlId?: string;
    sessionId?: string;
  },""",
)
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    """    void applyFillInstructions(message.instructions)
      .then((results) => {""",
    """    void applyFillInstructions(
      message.instructions,
      {},
      message.preferredRecipes ?? {},
    )
      .then((results) => {""",
)
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    """  if (message.type === \"APPLY_FILE_PICKER_ASSIST\" && message.controlId) {""",
    """  if (
    message.type === \"TEACH_BEGIN\" &&
    message.controlId &&
    message.sessionId
  ) {
    try {
      sendResponse({
        result: beginTeachInteraction(message.sessionId, message.controlId),
      });
    } catch (error) {
      sendResponse({
        error: error instanceof Error ? error.message : \"Teach MUNSHI could not start\",
      });
    }
    return false;
  }
  if (message.type === \"TEACH_FINISH\" && message.sessionId) {
    try {
      sendResponse({ result: finishTeachInteraction(message.sessionId) });
    } catch (error) {
      sendResponse({
        error: error instanceof Error ? error.message : \"Teach MUNSHI could not finish\",
      });
    }
    return false;
  }
  if (message.type === \"TEACH_CANCEL\" && message.sessionId) {
    sendResponse({ result: cancelTeachInteraction(message.sessionId) });
    return false;
  }
  if (message.type === \"APPLY_FILE_PICKER_ASSIST\" && message.controlId) {""",
)

replace_once(
    "apps/extension/src/messaging/native.ts",
    """export type InteractionRecipeStrategy =
  | \"ARIA_COMBOBOX\"
  | \"ARIA_RADIO\"
  | \"ARIA_BOOLEAN\"
  | \"CUSTOM_DATE\"
  | \"CUSTOM_MULTI_SELECT\";""",
    """export type InteractionRecipeStrategy =
  | \"ARIA_COMBOBOX\"
  | \"ARIA_RADIO\"
  | \"ARIA_BOOLEAN\"
  | \"CUSTOM_DATE\"
  | \"CUSTOM_MULTI_SELECT\"
  | \"TAUGHT_RECIPE\";""",
)
replace_once(
    "apps/extension/src/messaging/native.ts",
    """    \"CUSTOM_DATE\",
    \"CUSTOM_MULTI_SELECT\",
  ]);""",
    """    \"CUSTOM_DATE\",
    \"CUSTOM_MULTI_SELECT\",
    \"TAUGHT_RECIPE\",
  ]);""",
)
replace_once(
    "apps/extension/src/messaging/native.ts",
    """export async function recordInteractionRecipeAttempt(input: {
  attemptId: string;
  applicationId?: string | null;
  siteOrigin: string;
  componentFingerprint: string;
  semanticType: string;
  strategy: InteractionRecipeStrategy;
  success: boolean;
  verified: boolean;
  failureReason: string | null;
}): Promise<InteractionRecipeStatus> {
  const result = parseInteractionRecipe(
    await sendNative<unknown>({
      type: \"RECORD_INTERACTION_RECIPE_ATTEMPT\",
      payload: input,
    }),
  );
  if (!result) throw new Error(\"Native recipe attempt returned no recipe\");
  return result;
}""",
    """export async function recordInteractionRecipeAttempt(input: {
  attemptId: string;
  applicationId?: string | null;
  siteOrigin: string;
  componentFingerprint: string;
  semanticType: string;
  strategy: Exclude<InteractionRecipeStrategy, \"TAUGHT_RECIPE\">;
  success: boolean;
  verified: boolean;
  failureReason: string | null;
}): Promise<InteractionRecipeStatus> {
  const result = parseInteractionRecipe(
    await sendNative<unknown>({
      type: \"RECORD_INTERACTION_RECIPE_ATTEMPT\",
      payload: input,
    }),
  );
  if (!result) throw new Error(\"Native recipe attempt returned no recipe\");
  return result;
}

export async function teachInteractionRecipe(input: {
  attemptId: string;
  applicationId?: string | null;
  siteOrigin: string;
  componentFingerprint: string;
  semanticType: string;
  actions: unknown[];
}): Promise<InteractionRecipeStatus> {
  const result = parseInteractionRecipe(
    await sendNative<unknown>({
      type: \"TEACH_INTERACTION_RECIPE\",
      payload: input,
    }),
  );
  if (!result) throw new Error(\"Teach MUNSHI returned no candidate recipe\");
  return result;
}

export async function recordInteractionRecipeOutcome(input: {
  recipeId: string;
  attemptId: string;
  applicationId?: string | null;
  success: boolean;
  verified: boolean;
  failureReason: string | null;
}): Promise<InteractionRecipeStatus> {
  const result = parseInteractionRecipe(
    await sendNative<unknown>({
      type: \"RECORD_INTERACTION_RECIPE_OUTCOME\",
      payload: input,
    }),
  );
  if (!result) throw new Error(\"Recipe outcome returned no recipe\");
  return result;
}""",
)

replace_once(
    "apps/extension/src/messaging/client.ts",
    """    interaction_learning?: boolean;
    ai_settings?: boolean;""",
    """    interaction_learning?: boolean;
    teach_munshi?: boolean;
    ai_settings?: boolean;""",
)
replace_once(
    "apps/extension/src/messaging/client.ts",
    """    \"application_checkpoints\",
    \"ai_settings\",""",
    """    \"application_checkpoints\",
    \"interaction_learning\",
    \"teach_munshi\",
    \"ai_settings\",""",
)
replace_once(
    "apps/extension/src/messaging/client.ts",
    """  | {
      type: \"AUTOPILOT_ASSIST_FILE\";
      payload: { frameId: number; controlId: string };
    };""",
    """  | {
      type: \"AUTOPILOT_ASSIST_FILE\";
      payload: { frameId: number; controlId: string };
    }
  | {
      type: \"TEACH_BEGIN\";
      payload: { frameId: number; controlId: string; applicationId: string };
    }
  | {
      type: \"TEACH_FINISH\";
      payload: { frameId: number; sessionId: string; applicationId: string };
    }
  | {
      type: \"TEACH_CANCEL\";
      payload: { frameId: number; sessionId: string };
    };""",
)
replace_once(
    "apps/extension/src/messaging/client.ts",
    """export async function requestFilePickerAssist(
  frameId: number,
  controlId: string,
): Promise<{ status: string; reason: string }> {
  return (await send({
    type: \"AUTOPILOT_ASSIST_FILE\",
    payload: { frameId, controlId },
  })) as { status: string; reason: string };
}""",
    """export async function requestFilePickerAssist(
  frameId: number,
  controlId: string,
): Promise<{ status: string; reason: string }> {
  return (await send({
    type: \"AUTOPILOT_ASSIST_FILE\",
    payload: { frameId, controlId },
  })) as { status: string; reason: string };
}

export type TeachMunshiStart = {
  sessionId: string;
  controlId: string;
  label: string;
  componentFingerprint: string;
  startedAt: string;
};

export type TeachMunshiResult = {
  sessionId: string;
  controlId: string;
  changed: boolean;
  reusable: boolean;
  eventTypes: string[];
  recipe: null | {
    recipeId: string;
    state: \"SHADOW\" | \"PROMOTED\" | \"ROLLED_BACK\";
    version: number;
    verifiedAttempts?: number;
    verifiedSuccesses?: number;
  };
};

export async function beginTeachMunshi(
  frameId: number,
  controlId: string,
  applicationId: string,
): Promise<TeachMunshiStart> {
  return (await send({
    type: \"TEACH_BEGIN\",
    payload: { frameId, controlId, applicationId },
  })) as TeachMunshiStart;
}

export async function finishTeachMunshi(
  frameId: number,
  sessionId: string,
  applicationId: string,
): Promise<TeachMunshiResult> {
  return (await send({
    type: \"TEACH_FINISH\",
    payload: { frameId, sessionId, applicationId },
  })) as TeachMunshiResult;
}

export async function cancelTeachMunshi(
  frameId: number,
  sessionId: string,
): Promise<void> {
  await send({ type: \"TEACH_CANCEL\", payload: { frameId, sessionId } });
}""",
)

replace_once(
    "apps/extension/src/background/service-worker.ts",
    """  getPromotedInteractionRecipe,
  markAIDraftUsed,
  recordInteractionRecipeAttempt,""",
    """  getPromotedInteractionRecipe,
  markAIDraftUsed,
  recordInteractionRecipeAttempt,
  recordInteractionRecipeOutcome,
  teachInteractionRecipe,""",
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    """  | {
      type: \"AUTOPILOT_ASSIST_FILE\";
      payload: { frameId: number; controlId: string };
    };""",
    """  | {
      type: \"AUTOPILOT_ASSIST_FILE\";
      payload: { frameId: number; controlId: string };
    }
  | {
      type: \"TEACH_BEGIN\";
      payload: { frameId: number; controlId: string; applicationId: string };
    }
  | {
      type: \"TEACH_FINISH\";
      payload: { frameId: number; sessionId: string; applicationId: string };
    }
  | {
      type: \"TEACH_CANCEL\";
      payload: { frameId: number; sessionId: string };
    };""",
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    """  const response = await sendWithContentRecovery<
    { results?: FillResult[] } | undefined
  >(contentRuntimeApi, tabId, instruction.frameId, {
    type: \"APPLY_FILL_INSTRUCTIONS\",
    instructions: [instruction],
  });""",
    """  const preferredRecipes =
    promotedRecipe?.strategy === \"TAUGHT_RECIPE\" &&
    promotedRecipe.state !== \"ROLLED_BACK\"
      ? {
          [instruction.controlId]: {
            recipeId: promotedRecipe.recipeId,
            strategy: \"TAUGHT_RECIPE\" as const,
            actions: promotedRecipe.actions,
            state: promotedRecipe.state,
            version: promotedRecipe.version,
          },
        }
      : {};
  const response = await sendWithContentRecovery<
    { results?: FillResult[] } | undefined
  >(contentRuntimeApi, tabId, instruction.frameId, {
    type: \"APPLY_FILL_INSTRUCTIONS\",
    instructions: [instruction],
    preferredRecipes,
  });""",
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    """    results.map(async (result) => {
      const strategy = result.strategy as InteractionRecipeStrategy | undefined;
      if (
        !siteOrigin ||""",
    """    results.map(async (result) => {
      if (
        promotedRecipe &&
        result.recipeAttempted &&
        result.recipeId === promotedRecipe.recipeId
      ) {
        try {
          const learned = await recordInteractionRecipeOutcome({
            recipeId: promotedRecipe.recipeId,
            attemptId: crypto.randomUUID(),
            applicationId: null,
            success: result.status === \"FILLED\" && result.recipeSucceeded === true,
            verified: true,
            failureReason:
              result.status === \"FILLED\" && result.recipeSucceeded === true
                ? null
                : result.reason,
          });
          return {
            ...result,
            recipeId: learned.recipeId,
            recipeAttempted: true,
            recipeSucceeded: result.recipeSucceeded === true,
          };
        } catch {
          return result;
        }
      }
      const strategy = result.strategy as
        | Exclude<InteractionRecipeStrategy, \"TAUGHT_RECIPE\">
        | undefined;
      if (
        !siteOrigin ||""",
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    """async function sendFilePickerAssist(
  tabId: number,
  frameId: number,
  controlId: string,
): Promise<unknown> {""",
    r'''async function activeHttpTab(): Promise<chrome.tabs.Tab> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined || !/^https?:\/\//.test(tab.url ?? "")) {
    throw new Error("No active browser application tab found");
  }
  return tab;
}

async function beginTeach(
  frameId: number,
  controlId: string,
): Promise<unknown> {
  const tab = await activeHttpTab();
  await ensureTabContentRuntime(contentRuntimeApi, tab.id!);
  const sessionId = `teach-${crypto.randomUUID()}`;
  const response = await sendWithContentRecovery<
    { result?: unknown; error?: string } | undefined
  >(contentRuntimeApi, tab.id!, frameId, {
    type: "TEACH_BEGIN",
    sessionId,
    controlId,
  });
  if (response?.error) throw new Error(response.error);
  if (!response?.result) throw new Error("Teach MUNSHI did not start in the employer page");
  return response.result;
}

async function finishTeach(
  frameId: number,
  sessionId: string,
  applicationId: string,
): Promise<unknown> {
  const tab = await activeHttpTab();
  const response = await sendWithContentRecovery<
    {
      result?: {
        sessionId: string;
        controlId: string;
        componentFingerprint: string;
        changed: boolean;
        reusable: boolean;
        actions: unknown[];
        eventTypes: string[];
        startedAt: string;
        finishedAt: string;
      };
      error?: string;
    } | undefined
  >(contentRuntimeApi, tab.id!, frameId, {
    type: "TEACH_FINISH",
    sessionId,
  });
  if (response?.error) throw new Error(response.error);
  const capture = response?.result;
  if (!capture) throw new Error("Teach MUNSHI returned no demonstration capture");
  if (!capture.reusable) return { ...capture, recipe: null };

  const page = await getMergedPageForTab(tab.id!);
  if (!page) throw new Error("Application page changed before the demonstration was saved");
  const control = page.controls.find((item) => item.controlId === capture.controlId);
  const question = page.questions.find((item) => item.controlId === capture.controlId);
  if (!control || !control.componentFingerprint) {
    throw new Error("The demonstrated control changed before its recipe could be saved");
  }
  await ensureNativeApplication(applicationId, page.observedAt);
  const recipe = await teachInteractionRecipe({
    attemptId: `demo-${crypto.randomUUID()}`,
    applicationId,
    siteOrigin: new URL(page.url).origin,
    componentFingerprint: control.componentFingerprint,
    semanticType: question?.semanticType ?? "UNKNOWN",
    actions: capture.actions,
  });
  return { ...capture, recipe };
}

async function cancelTeach(frameId: number, sessionId: string): Promise<unknown> {
  const tab = await activeHttpTab();
  const response = await sendWithContentRecovery<{ result?: unknown } | undefined>(
    contentRuntimeApi,
    tab.id!,
    frameId,
    { type: "TEACH_CANCEL", sessionId },
  );
  return response?.result ?? { cancelled: false };
}

async function sendFilePickerAssist(
  tabId: number,
  frameId: number,
  controlId: string,
): Promise<unknown> {''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    """      case \"AUTOPILOT_STOP\":
        return {""",
    """      case \"TEACH_BEGIN\":
        return {
          ok: true,
          data: await beginTeach(request.payload.frameId, request.payload.controlId),
        };
      case \"TEACH_FINISH\":
        return {
          ok: true,
          data: await finishTeach(
            request.payload.frameId,
            request.payload.sessionId,
            request.payload.applicationId,
          ),
        };
      case \"TEACH_CANCEL\":
        return {
          ok: true,
          data: await cancelTeach(
            request.payload.frameId,
            request.payload.sessionId,
          ),
        };
      case \"AUTOPILOT_STOP\":
        return {""",
)

write(
    "apps/extension/src/sidepanel/TeachMunshiPanel.tsx",
    r'''import { useEffect, useMemo, useState } from "react";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  beginTeachMunshi,
  cancelTeachMunshi,
  finishTeachMunshi,
  type TeachMunshiStart,
} from "../messaging/client";

export function TeachMunshiPanel({
  page,
  applicationId,
  nativeAvailable,
  suggestedControlId,
}: {
  page: ApplicationPage;
  applicationId: string;
  nativeAvailable: boolean;
  suggestedControlId: string | null;
}) {
  const eligible = useMemo(
    () =>
      page.controls.filter(
        (control) =>
          control.visible &&
          !control.disabled &&
          !["FILE", "BUTTON"].includes(control.kind),
      ),
    [page.controls],
  );
  const [selected, setSelected] = useState("");
  const [active, setActive] = useState<TeachMunshiStart | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (active) return;
    if (suggestedControlId && eligible.some((item) => item.controlId === suggestedControlId)) {
      setSelected(suggestedControlId);
      return;
    }
    if (!eligible.some((item) => item.controlId === selected)) {
      setSelected(eligible[0]?.controlId ?? "");
    }
  }, [active, eligible, selected, suggestedControlId]);

  const labelFor = (controlId: string): string => {
    const control = eligible.find((item) => item.controlId === controlId);
    if (!control) return controlId;
    const question = page.questions.find((item) => item.controlId === controlId);
    return (
      question?.rawText ||
      control.label ||
      control.ariaLabel ||
      control.name ||
      control.kind
    );
  };

  async function start(): Promise<void> {
    const control = eligible.find((item) => item.controlId === selected);
    if (!control) return;
    setBusy(true);
    setMessage("");
    try {
      const session = await beginTeachMunshi(
        control.frameId,
        control.controlId,
        applicationId,
      );
      setActive(session);
      setMessage(
        "Teaching is recording interaction mechanics only. Complete this one control on the employer page, then click Learn this interaction.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Teach MUNSHI could not start");
    } finally {
      setBusy(false);
    }
  }

  async function finish(): Promise<void> {
    if (!active) return;
    const control = eligible.find((item) => item.controlId === active.controlId);
    if (!control) return;
    setBusy(true);
    try {
      const learned = await finishTeachMunshi(
        control.frameId,
        active.sessionId,
        applicationId,
      );
      setActive(null);
      if (!learned.reusable || !learned.recipe) {
        setMessage(
          "MUNSHI observed the interaction but could not infer a reusable safe recipe. You can continue manually; the application was not blocked.",
        );
        return;
      }
      setMessage(
        `Candidate recipe v${learned.recipe.version} saved in ${learned.recipe.state.toLowerCase()} mode. MUNSHI will try it on the matching control and promote it after verified success.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Teach MUNSHI could not save the demonstration");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(): Promise<void> {
    if (!active) return;
    const control = eligible.find((item) => item.controlId === active.controlId);
    setBusy(true);
    try {
      if (control) await cancelTeachMunshi(control.frameId, active.sessionId);
    } finally {
      setActive(null);
      setMessage("Teaching cancelled. Nothing was learned from that demonstration.");
      setBusy(false);
    }
  }

  return (
    <div className="cloud-connection">
      <strong>Teach MUNSHI</strong>
      <span>
        When a control does not work, show MUNSHI the interaction once. It stores
        the mechanics, not the answer you selected.
      </span>
      {eligible.length > 0 ? (
        <>
          <label>
            Control to teach
            <select
              value={active?.controlId ?? selected}
              disabled={busy || Boolean(active)}
              onChange={(event) => setSelected(event.target.value)}
            >
              {eligible.map((control) => (
                <option key={control.controlId} value={control.controlId}>
                  {labelFor(control.controlId)}
                </option>
              ))}
            </select>
          </label>
          {!active ? (
            <button
              className="quiet"
              type="button"
              disabled={busy || !nativeAvailable || !selected}
              onClick={() => void start()}
            >
              Teach selected control
            </button>
          ) : (
            <div className="record-actions">
              <button
                className="primary"
                type="button"
                disabled={busy}
                onClick={() => void finish()}
              >
                Learn this interaction
              </button>
              <button
                className="quiet"
                type="button"
                disabled={busy}
                onClick={() => void cancel()}
              >
                Cancel
              </button>
            </div>
          )}
        </>
      ) : (
        <span>No teachable controls are visible on this page.</span>
      )}
      {message && <span className={active ? "diagnostic-error" : ""}>{message}</span>}
    </div>
  );
}
''',
)

replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    'import type { ApplicationPage } from "@munshi-apply/contracts";',
    'import type { ApplicationPage } from "@munshi-apply/contracts";\nimport { TeachMunshiPanel } from "./TeachMunshiPanel";',
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    """          <div className=\"record-actions\">
            <button""",
    """          <TeachMunshiPanel
            page={page}
            applicationId={applicationId}
            nativeAvailable={nativeAvailable}
            suggestedControlId={
              status?.lastFillResult?.status === \"FAILED\"
                ? status.lastFillResult.controlId
                : null
            }
          />

          <div className=\"record-actions\">
            <button""",
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    """              {plan.optionalUnansweredCount > 0 && (
                <span>
                  {plan.optionalUnansweredCount} optional questions left blank
                </span>
              )}""",
    """              {plan.optionalReviewCount > 0 && (
                <span>
                  {plan.optionalReviewCount} optional answer
                  {plan.optionalReviewCount === 1 ? \"\" : \"s\"} saved for review ·
                  they do not block page progress
                </span>
              )}
              {plan.optionalUnansweredCount > 0 && (
                <span>
                  {plan.optionalUnansweredCount} optional questions left blank
                </span>
              )}""",
)

replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    '    "interaction_learning": True,\n',
    '    "interaction_learning": True,\n    "teach_munshi": True,\n',
)
replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    """    if message_type == \"RECORD_INTERACTION_RECIPE_ATTEMPT\":
        return {
            \"ok\": True,
            \"data\": InteractionRecipeService(database).record(message.get(\"payload\")),
        }

    if message_type in {""",
    """    if message_type == \"RECORD_INTERACTION_RECIPE_ATTEMPT\":
        return {
            \"ok\": True,
            \"data\": InteractionRecipeService(database).record(message.get(\"payload\")),
        }
    if message_type == \"TEACH_INTERACTION_RECIPE\":
        return {
            \"ok\": True,
            \"data\": InteractionRecipeService(database).teach(message.get(\"payload\")),
        }
    if message_type == \"RECORD_INTERACTION_RECIPE_OUTCOME\":
        return {
            \"ok\": True,
            \"data\": InteractionRecipeService(database).record_outcome(message.get(\"payload\")),
        }

    if message_type in {""",
)

write(
    "apps/native-host/src/munshi_apply_native/interaction_recipe_service.py",
    r'''from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from .database import Database
from .learning_analytics_store import LearningAnalyticsStore

_ALLOWED_STRATEGIES = {
    "ARIA_COMBOBOX",
    "ARIA_RADIO",
    "ARIA_BOOLEAN",
    "CUSTOM_DATE",
    "CUSTOM_MULTI_SELECT",
}
_BLOCKED_SEMANTIC_MARKERS = {
    "PASSWORD",
    "OTP",
    "MFA",
    "CAPTCHA",
    "IDENTITY_VERIFICATION",
    "AUTHENTICATION",
}
_ALLOWED_KEYS = {"ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"}
_ALLOWED_WAIT_STATES = {"OPTIONS_VISIBLE", "VALUE_COMMITTED"}
_ACTIONS: dict[str, list[dict[str, object]]] = {
    "ARIA_COMBOBOX": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "ARIA_RADIO": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "ARIA_BOOLEAN": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "CUSTOM_DATE": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "CUSTOM_MULTI_SELECT": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
}


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _site_origin(payload: dict[str, Any]) -> str:
    origin = _required(payload, "siteOrigin")
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("siteOrigin must be an http(s) origin")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("siteOrigin must not contain a path, query, or fragment")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{port}"


def _binding(payload: dict[str, Any]) -> tuple[str, str, str]:
    origin = _site_origin(payload)
    fingerprint = _required(payload, "componentFingerprint")
    if not fingerprint.startswith("cfp-"):
        raise ValueError("componentFingerprint is invalid")
    semantic_type = _required(payload, "semanticType").upper()
    if any(marker in semantic_type for marker in _BLOCKED_SEMANTIC_MARKERS):
        raise ValueError("Authentication/security controls cannot create interaction recipes")
    return origin, fingerprint, semantic_type


def _strategy(payload: dict[str, Any]) -> str:
    strategy = _required(payload, "strategy").upper()
    if strategy not in _ALLOWED_STRATEGIES:
        raise ValueError("Interaction strategy is not eligible for learning")
    return strategy


def _validate_actions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise ValueError("Taught recipe requires 1-16 actions")
    result: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("Taught recipe actions must be objects")
        action_type = raw.get("type")
        if action_type in {"FOCUS", "CLICK", "SELECT_EXACT_OPTION"}:
            result.append({"type": action_type})
            continue
        if action_type == "TYPE" and raw.get("valueSource") == "ANSWER":
            result.append({"type": "TYPE", "valueSource": "ANSWER"})
            continue
        if action_type == "KEY" and raw.get("key") in _ALLOWED_KEYS:
            result.append({"type": "KEY", "key": raw["key"]})
            continue
        if action_type == "WAIT_FOR_STATE" and raw.get("state") in _ALLOWED_WAIT_STATES:
            result.append({"type": "WAIT_FOR_STATE", "state": raw["state"]})
            continue
        raise ValueError("Taught recipe contains an unsupported or value-bearing action")
    return result


def _recipe_id(origin: str, fingerprint: str, semantic_type: str, strategy: str) -> str:
    digest = hashlib.sha256(
        f"{origin}\n{fingerprint}\n{semantic_type}\n{strategy}".encode()
    ).hexdigest()[:32]
    return f"recipe-{digest}"


def _taught_recipe_id(
    origin: str,
    fingerprint: str,
    semantic_type: str,
    version: int,
    actions: list[dict[str, object]],
) -> str:
    canonical = json.dumps(actions, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{origin}\n{fingerprint}\n{semantic_type}\n{version}\n{canonical}".encode()
    ).hexdigest()[:32]
    return f"recipe-{digest}"


def _strategy_for_actions(actions: object) -> str | None:
    if not isinstance(actions, list):
        return None
    for strategy, expected in _ACTIONS.items():
        if actions == expected:
            return strategy
    try:
        _validate_actions(actions)
    except ValueError:
        return None
    return "TAUGHT_RECIPE"


def _wire_recipe(row: dict[str, Any], strategy: str) -> dict[str, object]:
    return {
        "recipeId": row["recipe_id"],
        "componentFingerprint": row["component_fingerprint"],
        "semanticType": row["semantic_type"],
        "siteOrigin": row["site_origin"],
        "strategy": strategy,
        "state": row["state"],
        "version": row["version"],
        "actions": row["actions"],
    }


class InteractionRecipeService:
    """Learns verified widget mechanics without storing application answer values."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.store = LearningAnalyticsStore(database)

    def lookup(self, payload: object) -> dict[str, object] | None:
        if not isinstance(payload, dict):
            raise ValueError("Recipe lookup payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT recipe_id
                FROM interaction_recipes
                WHERE site_origin = ? AND component_fingerprint = ?
                  AND semantic_type = ? AND state IN ('PROMOTED', 'SHADOW')
                ORDER BY CASE state WHEN 'PROMOTED' THEN 0 ELSE 1 END,
                         version DESC, updated_at DESC
                """,
                (origin, fingerprint, semantic_type),
            ).fetchall()
        for row in rows:
            recipe = self.store.recipe(str(row["recipe_id"]))
            if recipe is None:
                continue
            strategy = _strategy_for_actions(recipe["actions"])
            if strategy is not None:
                return _wire_recipe(recipe, strategy)
        return None

    def _finalize_state(self, recipe_id: str) -> dict[str, object]:
        recipe = self.store.recipe(recipe_id)
        if recipe is None:
            raise RuntimeError("Interaction recipe disappeared")
        strategy = _strategy_for_actions(recipe["actions"])
        if strategy is None:
            raise ValueError("Stored interaction recipe is invalid")
        attempts = self.store.recipe_attempts(recipe_id)
        verified_attempts = [item for item in attempts if item["verified"]]
        state = str(recipe["state"])
        promotion_threshold = 2 if strategy == "TAUGHT_RECIPE" else 3
        if state == "SHADOW" and len(verified_attempts) >= promotion_threshold:
            if all(bool(item["success"]) for item in verified_attempts[-promotion_threshold:]):
                state = "PROMOTED"
        elif state == "PROMOTED" and len(verified_attempts) >= 2:
            if all(not bool(item["success"]) for item in verified_attempts[-2:]):
                state = "ROLLED_BACK"
        if state != recipe["state"]:
            now = datetime.now(UTC).isoformat()
            self.store.save_recipe(
                {
                    "recipe_id": recipe["recipe_id"],
                    "component_fingerprint": recipe["component_fingerprint"],
                    "semantic_type": recipe["semantic_type"],
                    "site_origin": recipe["site_origin"],
                    "actions": recipe["actions"],
                    "version": recipe["version"],
                    "state": state,
                    "created_at": recipe["created_at"],
                    "updated_at": now,
                }
            )
            recipe = self.store.recipe(recipe_id)
            if recipe is None:
                raise RuntimeError("Interaction recipe disappeared after state update")
        return {
            **_wire_recipe(recipe, strategy),
            "verifiedAttempts": len(verified_attempts),
            "verifiedSuccesses": sum(bool(item["success"]) for item in verified_attempts),
        }

    def _record_outcome(
        self,
        recipe_id: str,
        *,
        attempt_id: str,
        application_id: str | None,
        success: bool,
        verified: bool,
        failure_reason: str | None,
    ) -> dict[str, object]:
        if self.store.recipe(recipe_id) is None:
            raise ValueError("Interaction recipe does not exist")
        now = datetime.now(UTC).isoformat()
        inserted = self.store.record_recipe_attempt(
            {
                "attempt_id": attempt_id,
                "recipe_id": recipe_id,
                "application_id": application_id,
                "occurred_at": now,
                "success": success,
                "verified": verified,
                "failure_reason": failure_reason,
            }
        )
        return {**self._finalize_state(recipe_id), "attemptInserted": inserted}

    def teach(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Teach MUNSHI payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        actions = _validate_actions(payload.get("actions"))
        attempt_id = _required(payload, "attemptId")
        application_id = payload.get("applicationId")
        if application_id is not None and (
            not isinstance(application_id, str) or not application_id.strip()
        ):
            raise ValueError("applicationId must be a non-empty string when supplied")
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS version
                FROM interaction_recipes
                WHERE site_origin = ? AND component_fingerprint = ? AND semantic_type = ?
                """,
                (origin, fingerprint, semantic_type),
            ).fetchone()
        version = int(row["version"] if row is not None else 0) + 1
        now = datetime.now(UTC).isoformat()
        recipe_id = _taught_recipe_id(origin, fingerprint, semantic_type, version, actions)
        self.store.save_recipe(
            {
                "recipe_id": recipe_id,
                "component_fingerprint": fingerprint,
                "semantic_type": semantic_type,
                "site_origin": origin,
                "actions": actions,
                "version": version,
                "state": "SHADOW",
                "created_at": now,
                "updated_at": now,
            }
        )
        return self._record_outcome(
            recipe_id,
            attempt_id=attempt_id,
            application_id=application_id.strip() if isinstance(application_id, str) else None,
            success=True,
            verified=True,
            failure_reason=None,
        )

    def record_outcome(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Recipe outcome payload must be an object")
        recipe_id = _required(payload, "recipeId")
        attempt_id = _required(payload, "attemptId")
        application_id = payload.get("applicationId")
        if application_id is not None and (
            not isinstance(application_id, str) or not application_id.strip()
        ):
            raise ValueError("applicationId must be a non-empty string when supplied")
        success = payload.get("success")
        verified = payload.get("verified")
        if not isinstance(success, bool) or not isinstance(verified, bool):
            raise ValueError("Recipe outcome success and verified must be booleans")
        failure_reason = payload.get("failureReason")
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError("failureReason must be a string or null")
        return self._record_outcome(
            recipe_id,
            attempt_id=attempt_id,
            application_id=application_id.strip() if isinstance(application_id, str) else None,
            success=success,
            verified=verified,
            failure_reason=failure_reason.strip()
            if isinstance(failure_reason, str) and failure_reason.strip()
            else None,
        )

    def record(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Recipe attempt payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        strategy = _strategy(payload)
        attempt_id = _required(payload, "attemptId")
        application_id = payload.get("applicationId")
        if application_id is not None and (
            not isinstance(application_id, str) or not application_id.strip()
        ):
            raise ValueError("applicationId must be a non-empty string when supplied")
        success = payload.get("success")
        verified = payload.get("verified")
        if not isinstance(success, bool) or not isinstance(verified, bool):
            raise ValueError("Recipe attempt success and verified must be booleans")
        failure_reason = payload.get("failureReason")
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError("failureReason must be a string or null")
        recipe_id = _recipe_id(origin, fingerprint, semantic_type, strategy)
        now = datetime.now(UTC).isoformat()
        existing = self.store.recipe(recipe_id)
        if existing is None:
            self.store.save_recipe(
                {
                    "recipe_id": recipe_id,
                    "component_fingerprint": fingerprint,
                    "semantic_type": semantic_type,
                    "site_origin": origin,
                    "actions": _ACTIONS[strategy],
                    "version": 1,
                    "state": "SHADOW",
                    "created_at": now,
                    "updated_at": now,
                }
            )
        return self._record_outcome(
            recipe_id,
            attempt_id=attempt_id,
            application_id=application_id.strip() if isinstance(application_id, str) else None,
            success=success,
            verified=verified,
            failure_reason=failure_reason.strip()
            if isinstance(failure_reason, str) and failure_reason.strip()
            else None,
        )
''',
)

write(
    "apps/native-host/tests/test_interaction_recipe_service.py",
    r'''from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.interaction_recipe_service import InteractionRecipeService


def create_service(tmp_path: Path) -> tuple[Database, InteractionRecipeService]:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return database, InteractionRecipeService(database)


def insert_application(database: Database, application_id: str = "app-1") -> None:
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES (?, NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (application_id, now, now),
        )


def payload(attempt_id: str, *, success: bool = True) -> dict[str, object]:
    return {
        "attemptId": attempt_id,
        "applicationId": "app-1",
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-safe123",
        "semanticType": "COUNTRY",
        "strategy": "ARIA_COMBOBOX",
        "success": success,
        "verified": True,
        "failureReason": None if success else "verification failed",
    }


def binding(semantic_type: str = "COUNTRY") -> dict[str, object]:
    return {
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-safe123",
        "semanticType": semantic_type,
    }


def taught_actions() -> list[dict[str, object]]:
    return [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "TYPE", "valueSource": "ANSWER"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ]


def test_recipe_stays_shadow_then_promotes_after_three_verified_successes(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    first = service.record(payload("attempt-1"))
    second = service.record(payload("attempt-2"))
    third = service.record(payload("attempt-3"))
    assert first["state"] == "SHADOW"
    assert second["state"] == "SHADOW"
    assert third["state"] == "PROMOTED"
    promoted = service.lookup(binding())
    assert promoted is not None
    assert promoted["strategy"] == "ARIA_COMBOBOX"
    assert promoted["state"] == "PROMOTED"
    assert all("value" not in action for action in promoted["actions"])


def test_promoted_recipe_rolls_back_after_two_verified_failures(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    for index in range(3):
        service.record(payload(f"success-{index}"))
    promoted = service.lookup(binding())
    assert promoted is not None
    first_failure = service.record_outcome(
        {
            "recipeId": promoted["recipeId"],
            "attemptId": "failure-1",
            "applicationId": "app-1",
            "success": False,
            "verified": True,
            "failureReason": "verification failed",
        }
    )
    second_failure = service.record_outcome(
        {
            "recipeId": promoted["recipeId"],
            "attemptId": "failure-2",
            "applicationId": "app-1",
            "success": False,
            "verified": True,
            "failureReason": "verification failed",
        }
    )
    assert first_failure["state"] == "PROMOTED"
    assert second_failure["state"] == "ROLLED_BACK"
    assert service.lookup(binding()) is None


def test_duplicate_attempt_is_idempotent(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    first = service.record(payload("same-attempt"))
    duplicate = service.record(payload("same-attempt"))
    assert first["attemptInserted"] is True
    assert duplicate["attemptInserted"] is False
    assert duplicate["verifiedAttempts"] == 1


def test_teach_munshi_saves_value_free_shadow_recipe_and_promotes_after_trial(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    taught = service.teach(
        {
            **binding(),
            "attemptId": "owner-demo",
            "applicationId": "app-1",
            "actions": taught_actions(),
        }
    )
    assert taught["strategy"] == "TAUGHT_RECIPE"
    assert taught["state"] == "SHADOW"
    assert taught["verifiedAttempts"] == 1
    assert "United States" not in str(taught)
    candidate = service.lookup(binding())
    assert candidate is not None
    assert candidate["recipeId"] == taught["recipeId"]
    promoted = service.record_outcome(
        {
            "recipeId": taught["recipeId"],
            "attemptId": "automatic-trial",
            "applicationId": "app-1",
            "success": True,
            "verified": True,
            "failureReason": None,
        }
    )
    assert promoted["state"] == "PROMOTED"
    assert promoted["verifiedSuccesses"] == 2


def test_learning_mechanics_is_allowed_for_consequential_answer_types_but_not_security_controls(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    sponsorship = payload("sponsorship-widget")
    sponsorship["semanticType"] = "SPONSORSHIP_FUTURE"
    assert service.record(sponsorship)["state"] == "SHADOW"

    unsafe = payload("unsafe-security")
    unsafe["semanticType"] = "MFA"
    with pytest.raises(ValueError, match="security"):
        service.record(unsafe)

    unsupported = payload("unsupported")
    unsupported["strategy"] = "FINAL_SUBMIT"
    with pytest.raises(ValueError, match="not eligible"):
        service.record(unsupported)


def test_teach_rejects_value_bearing_or_unsupported_recipe_steps(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    with pytest.raises(ValueError, match="unsupported or value-bearing"):
        service.teach(
            {
                **binding(),
                "attemptId": "bad-demo",
                "applicationId": "app-1",
                "actions": [{"type": "TYPE", "value": "secret answer"}],
            }
        )


def test_requires_origin_not_full_application_url(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    request = payload("bad-origin")
    request["siteOrigin"] = "https://jobs.example.test/apply/123?token=x"
    with pytest.raises(ValueError, match="siteOrigin"):
        service.record(request)
''',
)

write(
    "docs/reports/PHASE_5_6_12_PRACTICAL_TRANCHE_2026-08-16.md",
    """# MUNSHI Apply — Phase 5 / Phase 6 / Phase 12 Practical Tranche

**Date:** 2026-08-16  
**Candidate:** 0.2.4  
**Architecture source:** Complete Master Architecture Plan 2.0

## Goal

Advance Universal Autofill, Multi-Page AutoPilot, and Teach-MUNSHI together so that real application work stays usable. Safety rules remain around truthful facts, security checkpoints, and final submission; ordinary incomplete fields, optional questions, unfamiliar widgets, and recoverable interaction failures should not unnecessarily stop the application.

## Phase 5 — Universal Autofill

- Existing native/ARIA/custom/date/multi-select filling remains the default engine.
- A taught interaction recipe can now be executed before the normal fallback interaction.
- If a taught recipe does not verify, MUNSHI falls back to its normal universal fill strategy instead of blindly trusting the recipe.
- Every taught-recipe attempt is verified and fed back into recipe confidence.
- Consequential questions may reuse learned *widget mechanics* because no answer value is stored in the recipe; authentication/security controls remain excluded.

## Phase 6 — Multi-Page AutoPilot

- Required review/unresolved items still stop navigation, but optional review items no longer block page progress.
- Required-field validation shown on an incomplete form no longer stops the entire session before approved fills are attempted.
- A normal fill-verification failure becomes a durable review pause rather than a fatal AutoPilot error. The owner can fix or teach the control and Resume.
- A forward-navigation interaction that cannot be verified becomes a recoverable review pause rather than destroying the session.
- Interrupted fills and ordinary verification timeouts preserve state and surface a resume path when the application page is still available.
- CAPTCHA/MFA/OTP/identity/authentication boundaries and final employer submission remain explicit owner checkpoints.

## Phase 12 — Teach-MUNSHI

Teach-MUNSHI is visible directly inside AutoPilot rather than hidden in Settings.

Flow:

1. Select a visible control.
2. Click **Teach selected control**.
3. Perform that one interaction on the employer page.
4. Click **Learn this interaction**.
5. MUNSHI stores a value-free action recipe in SHADOW state.
6. On the next matching control, MUNSHI tries the taught recipe and verifies the result.
7. One owner demonstration plus one verified automatic success promotes the recipe.
8. Two consecutive verified failures roll a promoted recipe back.

The capture stores interaction mechanics and event classes, not the selected answer text. Recipe actions can reference the future resolved `ANSWER`, but cannot embed the demonstrated value.

## Practical operating principle

Guardrails should prevent incorrect claims, irreversible submission, credential/security abuse, and silent changes to protected facts. They should not turn routine application friction into a dead end. Recoverable form failures therefore pause with an obvious next action: correct manually, Teach MUNSHI, or Resume.
""",
)

print("Phase 5/6/12 practical tranche applied")
