import { resolveControlElement } from "./scanner";

export type FocusControlResult = {
  status: "FOCUSED" | "NOT_FOUND";
  reason: string;
  rebound?: boolean;
};

export type ReadControlValueResult = {
  status: "READ" | "EMPTY" | "NOT_FOUND";
  value: string;
  reason: string;
  rebound?: boolean;
};

const HIGHLIGHT_ATTRIBUTE = "data-munshi-owner-focus";
const HIGHLIGHT_DURATION_MS = 1_600;

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function labelText(input: HTMLInputElement): string {
  return Array.from(input.labels ?? [])
    .map((label) => compact(label.textContent))
    .filter(Boolean)
    .join(" ");
}

function radioValue(input: HTMLInputElement): string {
  const root = input.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) {
    return input.checked ? compact(labelText(input) || input.value) : "";
  }
  const candidates = Array.from(
    root.querySelectorAll<HTMLInputElement>("input[type='radio']"),
  ).filter((candidate) => !input.name || candidate.name === input.name);
  const selected = candidates.find((candidate) => candidate.checked);
  return selected ? compact(labelText(selected) || selected.value) : "";
}

function currentValue(element: HTMLElement): string {
  if (element instanceof HTMLInputElement) {
    if (element.type === "radio") return radioValue(element);
    if (element.type === "checkbox") return element.checked ? "Yes" : "No";
    return compact(element.value);
  }
  if (element instanceof HTMLSelectElement) {
    if (element.multiple) {
      return Array.from(element.selectedOptions)
        .map((option) => compact(option.textContent || option.value))
        .filter(Boolean)
        .join(", ");
    }
    const option = element.selectedOptions[0];
    return compact(option?.textContent || element.value);
  }
  if (element instanceof HTMLTextAreaElement) return compact(element.value);
  if (element.isContentEditable) return compact(element.textContent);
  return compact(
    element.getAttribute("aria-valuetext") ||
      element.getAttribute("data-value") ||
      element.getAttribute("value") ||
      element.textContent,
  ).slice(0, 2_000);
}

function highlight(element: HTMLElement): void {
  const token = crypto.randomUUID();
  const previousOutline = element.style.outline;
  const previousOutlineOffset = element.style.outlineOffset;
  element.setAttribute(HIGHLIGHT_ATTRIBUTE, token);
  element.style.outline = "3px solid Highlight";
  element.style.outlineOffset = "4px";
  window.setTimeout(() => {
    if (element.getAttribute(HIGHLIGHT_ATTRIBUTE) !== token) return;
    element.removeAttribute(HIGHLIGHT_ATTRIBUTE);
    element.style.outline = previousOutline;
    element.style.outlineOffset = previousOutlineOffset;
  }, HIGHLIGHT_DURATION_MS);
}

export function focusControlForOwner(controlId: string): FocusControlResult {
  const resolved = resolveControlElement(controlId);
  if (!(resolved?.element instanceof HTMLElement)) {
    return {
      status: "NOT_FOUND",
      reason: "The employer field changed before MUNSHI could focus it.",
    };
  }
  const element = resolved.element;
  element.scrollIntoView?.({ behavior: "smooth", block: "center", inline: "nearest" });
  try {
    element.focus({ preventScroll: true });
  } catch {
    element.focus();
  }
  highlight(element);
  return {
    status: "FOCUSED",
    reason: resolved.rebound
      ? "Field rebound after the employer page changed, then focused."
      : "Field focused without changing its value.",
    rebound: resolved.rebound,
  };
}

export function readControlValueForTeach(controlId: string): ReadControlValueResult {
  const resolved = resolveControlElement(controlId);
  if (!(resolved?.element instanceof HTMLElement)) {
    return {
      status: "NOT_FOUND",
      value: "",
      reason: "The demonstrated field is no longer available.",
    };
  }
  const value = currentValue(resolved.element);
  return {
    status: value ? "READ" : "EMPTY",
    value,
    reason: value
      ? "Owner-demonstrated value read transiently for approved memory/profile promotion."
      : "The demonstrated field has no committed value to remember.",
    rebound: resolved.rebound,
  };
}
