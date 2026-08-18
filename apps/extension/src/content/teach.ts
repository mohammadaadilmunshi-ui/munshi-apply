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

type TeachEventTarget = "control" | "control-group" | "owned-popup";

type ActiveTeachSession = TeachInteractionStart & {
  element: HTMLElement;
  resolvedControlId: string;
  controlKind: string;
  beforeMarker: string;
  eventTypes: Set<string>;
  eventSequence: { type: string; target: TeachEventTarget; atMs: number }[];
  startedAtMs: number;
  controlEngaged: boolean;
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

function radioGroup(element: HTMLInputElement): HTMLInputElement[] {
  if (element.type !== "radio" || !element.name) return [element];
  const root = element.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return [element];
  return Array.from(
    root.querySelectorAll<HTMLInputElement>("input[type='radio']"),
  ).filter((candidate) => candidate.name === element.name);
}

function customControlShellText(element: HTMLElement): string {
  if (!isPopupChoiceControl(element)) return "";
  const pieces: string[] = [];
  let current: HTMLElement | null = element;
  for (let depth = 0; current && depth < 3; depth += 1) {
    const text = compact(current.textContent);
    if (text) pieces.push(text);
    current = current.parentElement;
  }
  return pieces.join(" | ").slice(0, 4_000);
}

function controlValue(element: HTMLElement): string {
  const values: string[] = [];
  if (element instanceof HTMLInputElement) {
    values.push(element.value);
    if (element.type === "radio") {
      const selected = radioGroup(element).find(
        (candidate) => candidate.checked,
      );
      values.push(selected?.value ?? "");
    }
  } else if (element instanceof HTMLSelectElement) {
    values.push(element.value);
    values.push(
      Array.from(element.selectedOptions)
        .map((option) => compact(option.textContent))
        .join(" | "),
    );
  } else if (element instanceof HTMLTextAreaElement) {
    values.push(element.value);
  } else {
    values.push(element.textContent ?? "");
  }
  values.push(
    element.getAttribute("aria-valuetext") ?? "",
    element.getAttribute("data-value") ?? "",
    element.getAttribute("aria-activedescendant") ?? "",
    customControlShellText(element),
  );
  return compact(values.filter(Boolean).join(" | ")).slice(0, 8_000);
}

function safeStateFor(element: HTMLElement): Record<string, unknown> {
  const input = element instanceof HTMLInputElement ? element : null;
  const select = element instanceof HTMLSelectElement ? element : null;
  const textarea = element instanceof HTMLTextAreaElement ? element : null;
  const value = controlValue(element);
  const selectedRadio =
    input?.type === "radio"
      ? radioGroup(input).some((candidate) => candidate.checked)
      : undefined;
  return {
    valuePresent: value.length > 0,
    valueLength: value.length,
    checked: input?.checked ?? element.getAttribute("aria-checked"),
    groupChecked: selectedRadio,
    selected: element.getAttribute("aria-selected"),
    expanded: element.getAttribute("aria-expanded"),
    activeDescendantPresent: Boolean(
      element.getAttribute("aria-activedescendant"),
    ),
    dataValuePresent: Boolean(element.getAttribute("data-value")),
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

function optionLike(target: Element): boolean {
  return Boolean(
    target.closest(
      '[role="option"],[role="menuitem"],[role="treeitem"],[role="gridcell"],[data-value]',
    ),
  );
}

function eventTargetKind(
  element: HTMLElement,
  target: Element | null,
  allowPortalOption: boolean,
): TeachEventTarget | null {
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

  if (isPopupChoiceControl(element)) {
    if (
      (element.getAttribute("aria-expanded") === "true" ||
        document.activeElement === element) &&
      optionLike(target)
    ) {
      return "owned-popup";
    }
    if (allowPortalOption && optionLike(target)) return "owned-popup";
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

function compatibleControlKind(original: string, candidate: string): boolean {
  if (original === candidate) return true;
  const choiceKinds = new Set(["COMBOBOX", "SELECT"]);
  return choiceKinds.has(original) && choiceKinds.has(candidate);
}

function tryRebind(
  session: ActiveTeachSession,
  controlId: string,
): HTMLElement | null {
  const rebound = resolveControlElement(controlId);
  if (!(rebound?.element instanceof HTMLElement) || !teachable(rebound.element)) {
    return null;
  }
  if (!compatibleControlKind(session.controlKind, rebound.control.kind)) {
    return null;
  }
  session.element = rebound.element;
  session.resolvedControlId = rebound.control.controlId;
  return rebound.element;
}

function resolveLiveElement(session: ActiveTeachSession): HTMLElement {
  const exact = tryRebind(session, session.controlId);
  if (exact) return exact;

  const controls = scanDocument().controls;
  const fingerprintCandidates = controls.filter(
    (control) =>
      control.componentFingerprint === session.componentFingerprint &&
      compatibleControlKind(session.controlKind, control.kind) &&
      (!session.label || controlLabel(control) === session.label),
  );
  if (fingerprintCandidates.length === 1) {
    const rebound = tryRebind(session, fingerprintCandidates[0]!.controlId);
    if (rebound) return rebound;
  }

  if (session.label) {
    const labelCandidates = controls.filter(
      (control) =>
        controlLabel(control) === session.label &&
        compatibleControlKind(session.controlKind, control.kind),
    );
    if (labelCandidates.length === 1) {
      const rebound = tryRebind(session, labelCandidates[0]!.controlId);
      if (rebound) return rebound;
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
    ["radio", "checkbox", "switch"].includes(
      element.getAttribute("role") ?? "",
    )
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

function controlClickIsCommit(element: HTMLElement): boolean {
  if (element instanceof HTMLInputElement) {
    return ["radio", "checkbox"].includes(element.type);
  }
  return ["radio", "checkbox", "switch"].includes(
    element.getAttribute("role") ?? "",
  );
}

function explicitCommitObserved(
  element: HTMLElement,
  events: readonly { type: string; target: TeachEventTarget }[],
): boolean {
  return events.some((event) => {
    if (
      ["input", "change"].includes(event.type) &&
      (event.target === "control" || event.target === "control-group")
    ) {
      return true;
    }
    if (
      event.type === "click" &&
      ["owned-popup", "control-group"].includes(event.target)
    ) {
      return true;
    }
    if (
      event.type === "click" &&
      event.target === "control" &&
      controlClickIsCommit(element)
    ) {
      return true;
    }
    return event.type === "key:Enter";
  });
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
  const eventSequence: {
    type: string;
    target: TeachEventTarget;
    atMs: number;
  }[] = [];
  const startedAtMs = performance.now();
  const options = { capture: true, signal: abortController.signal } as const;
  const label = controlLabel(resolved.control);

  const session: ActiveTeachSession = {
    sessionId,
    controlId,
    resolvedControlId: controlId,
    label,
    componentFingerprint,
    controlKind: resolved.control.kind,
    startedAt: new Date().toISOString(),
    element,
    beforeMarker: marker(element),
    eventTypes,
    eventSequence,
    startedAtMs,
    controlEngaged: false,
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
        const targetKind = eventTargetKind(live, target, active.controlEngaged);
        if (!targetKind) return;
        if (
          targetKind === "control" &&
          ["focus", "click", "keydown"].includes(eventName)
        ) {
          active.controlEngaged = true;
        }
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
    beforeInternal.groupChecked !== afterInternal.groupChecked ||
    beforeInternal.selected !== afterInternal.selected;
  const explicitCommit = explicitCommitObserved(live, current.eventSequence);
  const mechanicsObserved =
    actions.length > 0 && current.eventSequence.length > 0;
  const valueCommitted = explicitCommit || (changed && answerStateChanged);
  const reasons: string[] = [];
  if (changed) reasons.push("control-state-changed");
  if (answerStateChanged) reasons.push("answer-state-changed");
  if (explicitCommit) reasons.push("explicit-commit-observed");
  if (mechanicsObserved) reasons.push("mechanics-pattern-observed");
  if (valueCommitted) reasons.push("value-commit-observed");
  if (!changed && explicitCommit) reasons.push("same-value-demonstration");
  if (current.eventSequence.length > 0)
    reasons.push("targeted-events-observed");
  if (current.resolvedControlId !== current.controlId)
    reasons.push("dynamic-control-rebound");
  const score = Math.min(
    1,
    (changed ? 0.2 : 0) +
      (answerStateChanged ? 0.2 : 0) +
      (explicitCommit ? 0.55 : 0) +
      (mechanicsObserved ? 0.25 : 0) +
      (current.eventSequence.length > 0 ? 0.2 : 0) +
      (current.resolvedControlId !== current.controlId ? 0.05 : 0),
  );
  const result: TeachInteractionCapture = {
    sessionId: current.sessionId,
    controlId: current.controlId,
    resolvedControlId: current.resolvedControlId,
    componentFingerprint: current.componentFingerprint,
    changed,
    reusable: score >= 0.8 && valueCommitted && actions.length > 0,
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
