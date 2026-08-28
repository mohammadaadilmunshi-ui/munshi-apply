import { resolveControlElement, scanDocument } from "./scanner";

export type OwnerFocusResult = {
  status: "FOCUSED" | "FAILED";
  controlId: string;
  rebound: boolean;
  reason: string;
};

export type OwnerReliabilityMessageResult =
  | { handled: false }
  | { handled: true; response: unknown };

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function inputLabel(element: HTMLInputElement): string {
  return compact(
    Array.from(element.labels ?? [])
      .map((label) => compact(label.textContent))
      .filter(Boolean)
      .join(" "),
  );
}

function selectedRadioValue(element: HTMLInputElement): string {
  const root = element.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return "";
  const selected = Array.from(
    root.querySelectorAll<HTMLInputElement>("input[type='radio']"),
  ).find(
    (candidate) =>
      candidate.checked && (!element.name || candidate.name === element.name),
  );
  if (!selected) return "";
  return inputLabel(selected) || compact(selected.value);
}

export function ownerControlValue(element: Element): string {
  if (element instanceof HTMLSelectElement) {
    const selected = Array.from(element.selectedOptions)
      .map((option) => compact(option.textContent) || compact(option.value))
      .filter(Boolean);
    return compact(selected.join(" | ") || element.value).slice(0, 4_000);
  }
  if (element instanceof HTMLInputElement) {
    const type = element.type.toLocaleLowerCase("en-US");
    if (type === "radio") return selectedRadioValue(element).slice(0, 4_000);
    if (type === "checkbox") return element.checked ? "Yes" : "No";
    return compact(element.value).slice(0, 4_000);
  }
  if (element instanceof HTMLTextAreaElement) {
    return compact(element.value).slice(0, 4_000);
  }
  if (element instanceof HTMLElement) {
    return compact(
      element.getAttribute("aria-valuetext") ||
        element.getAttribute("data-value") ||
        (element.isContentEditable ? element.textContent : "") ||
        element.getAttribute("value") ||
        element.textContent,
    ).slice(0, 4_000);
  }
  return "";
}

export function focusOwnerControl(controlId: string): OwnerFocusResult {
  const resolved = resolveControlElement(controlId);
  if (!(resolved?.element instanceof HTMLElement)) {
    return {
      status: "FAILED",
      controlId,
      rebound: false,
      reason: "The employer field is no longer available on this page.",
    };
  }

  const element = resolved.element;
  element.scrollIntoView?.({
    behavior: "smooth",
    block: "center",
    inline: "nearest",
  });
  try {
    element.focus({ preventScroll: true });
  } catch {
    element.focus();
  }

  const previousOutline = element.style.outline;
  const previousOutlineOffset = element.style.outlineOffset;
  element.style.outline = "3px solid Highlight";
  element.style.outlineOffset = "3px";
  window.setTimeout(() => {
    if (!element.isConnected) return;
    element.style.outline = previousOutline;
    element.style.outlineOffset = previousOutlineOffset;
  }, 1_800);

  return {
    status: "FOCUSED",
    controlId: resolved.control.controlId,
    rebound: resolved.rebound,
    reason: resolved.rebound
      ? "Field found after the employer page re-rendered it."
      : "Field opened and focused.",
  };
}

/**
 * Handles owner-facing content messages without registering its own runtime
 * listener. bootstrap.ts owns the single disposable content listener so an
 * extension recovery re-injection cannot accumulate parallel listeners.
 */
export function handleOwnerReliabilityMessage(
  message: unknown,
): OwnerReliabilityMessageResult {
  if (!message || typeof message !== "object") return { handled: false };
  const candidate = message as { type?: unknown; controlId?: unknown };

  if (
    candidate.type === "MUNSHI_OWNER_FOCUS_CONTROL" &&
    typeof candidate.controlId === "string"
  ) {
    return {
      handled: true,
      response: {
        ok: true,
        result: focusOwnerControl(candidate.controlId),
      },
    };
  }

  if (
    candidate.type === "MUNSHI_OWNER_READ_CONTROL_VALUE" &&
    typeof candidate.controlId === "string"
  ) {
    const resolved = resolveControlElement(candidate.controlId);
    return {
      handled: true,
      response: {
        ok: Boolean(resolved),
        value: resolved ? ownerControlValue(resolved.element) : "",
        rebound: resolved?.rebound ?? false,
      },
    };
  }

  if (candidate.type === "MUNSHI_OWNER_PAGE_CONTEXT") {
    return {
      handled: true,
      response: { ok: true, page: scanDocument() },
    };
  }

  return { handled: false };
}
