import type { RecipeAction } from "@munshi-apply/application-model";
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
    value:
      input?.value ??
      select?.value ??
      textarea?.value ??
      element.textContent ??
      "",
  });
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
  if (!(element instanceof HTMLElement) || !teachable(element)) {
    throw new Error(
      "This employer control is not eligible for Teach MUNSHI. File/security/final actions stay owner-operated.",
    );
  }
  const componentFingerprint = resolved?.control.componentFingerprint ?? "";
  if (!componentFingerprint) {
    throw new Error(
      "This control does not have a reusable component fingerprint yet",
    );
  }
  const abortController = new AbortController();
  const eventTypes = new Set<string>();
  const options = { capture: true, signal: abortController.signal } as const;
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
        if (eventName === "keydown" && event instanceof KeyboardEvent) {
          if (
            !["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(
              event.key,
            )
          ) {
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
      resolved?.control.label ||
        resolved?.control.ariaLabel ||
        resolved?.control.name,
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

export function finishTeachInteraction(
  sessionId: string,
): TeachInteractionCapture {
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

export function cancelTeachInteraction(sessionId: string): {
  cancelled: boolean;
} {
  if (!active || active.sessionId !== sessionId) return { cancelled: false };
  dispose();
  return { cancelled: true };
}
