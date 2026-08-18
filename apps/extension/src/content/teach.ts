import type { RecipeAction } from "@munshi-apply/application-model";
import { isAriaMultiSelectControl } from "./advanced-controls";
import { isPopupChoiceControl } from "./adaptive";
import { resolveControlElement, scanDocument } from "./scanner";

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
  resolvedControlId: string;
  componentFingerprint: string;
  changed: boolean;
  reusable: boolean;
  actions: RecipeAction[];
  eventTypes: string[];
  eventSequence: { type: string; target: string; atMs: number }[];
  beforeState: Record<string, unknown>;
  afterState: Record<string, unknown>;
  quality: { score: number; reasons: string[]; valueCommitted: boolean };
  startedAt: string;
  finishedAt: string;
};

type ActiveTeachSession = TeachInteractionStart & {
  element: HTMLElement;
  resolvedControlId: string;
  beforeMarker: string;
  eventTypes: Set<string>;
  eventSequence: { type: string; target: string; atMs: number }[];
  startedAtMs: number;
  abortController: AbortController;
};

type InternalTeachState = Record<string, unknown> & { __privateValue?: string };

let active: ActiveTeachSession | null = null;

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function controlLabel(control: {
  label?: string | null;
  ariaLabel?: string | null;
  name?: string | null;
}): string {
  return compact(control.label || control.ariaLabel || control.name);
}

function controlValue(element: HTMLElement): string {
  if (element instanceof HTMLInputElement) return element.value;
  if (element instanceof HTMLSelectElement) return element.value;
  if (element instanceof HTMLTextAreaElement) return element.value;
  return element.textContent ?? "";
}

function safeStateFor(element: HTMLElement): Record<string, unknown> {
  const input = element instanceof HTMLInputElement ? element : null;
  const select = element instanceof HTMLSelectElement ? element : null;
  const textarea = element instanceof HTMLTextAreaElement ? element : null;
  const value = controlValue(element);
  return {
    valuePresent: value.length > 0,
    valueLength: value.length,
    checked: input?.checked ?? element.getAttribute("aria-checked"),
    selected: element.getAttribute("aria-selected"),
    expanded: element.getAttribute("aria-expanded"),
    invalid: element.getAttribute("aria-invalid"),
    disabled:
      input?.disabled ??
      select?.disabled ??
      textarea?.disabled ??
      element.getAttribute("aria-disabled"),
    role: element.getAttribute("role"),
  };
}

function marker(element: HTMLElement): string {
  return JSON.stringify({
    ...safeStateFor(element),
    __privateValue: controlValue(element),
  });
}

function parseInternalMarker(value: string): InternalTeachState {
  return JSON.parse(value) as InternalTeachState;
}

function redactedMarkerState(value: string): Record<string, unknown> {
  const parsed = parseInternalMarker(value);
  delete parsed.__privateValue;
  return parsed;
}

function popupIds(element: HTMLElement): string[] {
  return [
    element.getAttribute("aria-controls"),
    element.getAttribute("aria-owns"),
  ]
    .flatMap((value) => (value ?? "").split(/\s+/))
    .filter(Boolean);
}

function eventTargetKind(
  element: HTMLElement,
  target: Element | null,
): "control" | "control-group" | "owned-popup" | null {
  if (!target) return null;
  if (target === element || element.contains(target)) return "control";

  const explicitPopupIds = popupIds(element);
  let cursor: Element | null = target;
  while (cursor) {
    if (cursor.id && explicitPopupIds.includes(cursor.id)) return "owned-popup";
    cursor = cursor.parentElement;
  }

  const inputType =
    element instanceof HTMLInputElement
      ? element.type.toLocaleLowerCase("en-US")
      : "";
  const role = element.getAttribute("role") ?? "";
  if (
    ["radio", "checkbox"].includes(inputType) ||
    ["radio", "checkbox", "switch"].includes(role)
  ) {
    const group = element.closest(
      'fieldset,[role="radiogroup"],[role="group"]',
    );
    if (group?.contains(target)) return "control-group";
  }

  if (
    isPopupChoiceControl(element) &&
    (element.getAttribute("aria-expanded") === "true" ||
      document.activeElement === element)
  ) {
    const option = target.closest(
      '[role="option"],[role="menuitem"],[role="treeitem"],[data-value]',
    );
    if (option) return "owned-popup";
  }

  return null;
}

function teachable(element: HTMLElement): boolean {
  if (element instanceof HTMLInputElement) {
    return ![
      "file",
      "password",
      "hidden",
      "submit",
      "button",
      "reset",
    ].includes(element.type);
  }
  if (element instanceof HTMLButtonElement) return false;
  return true;
}

function resolveLiveElement(session: ActiveTeachSession): HTMLElement {
  if (session.element.isConnected) return session.element;

  const exact = resolveControlElement(session.controlId);
  if (exact?.element instanceof HTMLElement && teachable(exact.element)) {
    session.element = exact.element;
    session.resolvedControlId = exact.control.controlId;
    return exact.element;
  }

  const candidates = scanDocument().controls.filter(
    (control) =>
      control.componentFingerprint === session.componentFingerprint &&
      (!session.label || controlLabel(control) === session.label),
  );
  if (candidates.length === 1) {
    const rebound = resolveControlElement(candidates[0]!.controlId);
    if (rebound?.element instanceof HTMLElement && teachable(rebound.element)) {
      session.element = rebound.element;
      session.resolvedControlId = rebound.control.controlId;
      return rebound.element;
    }
  }

  return session.element;
}

function inferredActions(
  element: HTMLElement,
  eventTypes: Set<string>,
): RecipeAction[] {
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
  if (!resolved || !(element instanceof HTMLElement) || !teachable(element)) {
    throw new Error(
      "This employer control is not eligible for Teach MUNSHI. File/security/final actions stay owner-operated.",
    );
  }
  const componentFingerprint = resolved.control.componentFingerprint ?? "";
  if (!componentFingerprint) {
    throw new Error(
      "This control does not have a reusable component fingerprint yet",
    );
  }
  const abortController = new AbortController();
  const eventTypes = new Set<string>();
  const eventSequence: { type: string; target: string; atMs: number }[] = [];
  const startedAtMs = performance.now();
  const options = { capture: true, signal: abortController.signal } as const;
  const label = controlLabel(resolved.control);

  const session: ActiveTeachSession = {
    sessionId,
    controlId,
    resolvedControlId: controlId,
    label,
    componentFingerprint,
    startedAt: new Date().toISOString(),
    element,
    beforeMarker: marker(element),
    eventTypes,
    eventSequence,
    startedAtMs,
    abortController,
  };
  active = session;

  for (const eventName of [
    "focus",
    "click",
    "input",
    "change",
    "keydown",
    "blur",
  ]) {
    document.addEventListener(
      eventName,
      (event) => {
        if (!active || active.sessionId !== sessionId) return;
        const live = resolveLiveElement(active);
        const target = event.target instanceof Element ? event.target : null;
        const targetKind = eventTargetKind(live, target);
        if (!targetKind) return;
        if (eventName === "keydown" && event instanceof KeyboardEvent) {
          if (
            !["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(
              event.key,
            )
          ) {
            return;
          }
          const eventType = `key:${event.key}`;
          eventTypes.add(eventType);
          if (eventSequence.length < 60) {
            eventSequence.push({
              type: eventType,
              target: targetKind,
              atMs: Math.round(performance.now() - startedAtMs),
            });
          }
          return;
        }
        eventTypes.add(eventName);
        if (eventSequence.length < 60) {
          eventSequence.push({
            type: eventName,
            target: targetKind,
            atMs: Math.round(performance.now() - startedAtMs),
          });
        }
      },
      options,
    );
  }

  element.scrollIntoView?.({ block: "center", inline: "nearest" });
  return {
    sessionId,
    controlId,
    label,
    componentFingerprint,
    startedAt: session.startedAt,
  };
}

export function finishTeachInteraction(
  sessionId: string,
): TeachInteractionCapture {
  if (!active || active.sessionId !== sessionId) {
    throw new Error("Teach MUNSHI session is no longer active in this frame");
  }
  const current = active;
  const live = resolveLiveElement(current);
  const actions = inferredActions(live, current.eventTypes);
  const afterMarker = marker(live);
  const beforeInternal = parseInternalMarker(current.beforeMarker);
  const afterInternal = parseInternalMarker(afterMarker);
  const changed = current.beforeMarker !== afterMarker;
  const answerStateChanged =
    beforeInternal.__privateValue !== afterInternal.__privateValue ||
    beforeInternal.checked !== afterInternal.checked ||
    beforeInternal.selected !== afterInternal.selected;
  const commitEventObserved =
    current.eventTypes.has("change") ||
    current.eventTypes.has("input") ||
    current.eventTypes.has("click") ||
    current.eventTypes.has("key:Enter");
  const valueCommitted = changed && answerStateChanged && commitEventObserved;
  const reasons: string[] = [];
  if (changed) reasons.push("control-state-changed");
  if (answerStateChanged) reasons.push("answer-state-changed");
  if (valueCommitted) reasons.push("value-commit-observed");
  if (current.eventSequence.length > 0)
    reasons.push("targeted-events-observed");
  if (current.resolvedControlId !== current.controlId)
    reasons.push("dynamic-control-rebound");
  const score = Math.min(
    1,
    (changed ? 0.3 : 0) +
      (answerStateChanged ? 0.3 : 0) +
      (valueCommitted ? 0.25 : 0) +
      (current.eventSequence.length > 0 ? 0.15 : 0),
  );
  const result: TeachInteractionCapture = {
    sessionId: current.sessionId,
    controlId: current.controlId,
    resolvedControlId: current.resolvedControlId,
    componentFingerprint: current.componentFingerprint,
    changed,
    reusable: score >= 0.8 && actions.length > 0,
    actions,
    eventTypes: [...current.eventTypes],
    eventSequence: current.eventSequence.slice(0, 60),
    beforeState: redactedMarkerState(current.beforeMarker),
    afterState: redactedMarkerState(afterMarker),
    quality: { score, reasons, valueCommitted },
    startedAt: current.startedAt,
    finishedAt: new Date().toISOString(),
  };
  dispose();
  return result;
}

export function cancelTeachInteraction(sessionId: string): {
  cancelled: boolean;
} {
  if (!active || active.sessionId !== sessionId) return { cancelled: false };
  dispose();
  return { cancelled: true };
}
