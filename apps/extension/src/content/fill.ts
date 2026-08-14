import type { FillInstruction, FillResult } from "@munshi-apply/contracts";
import { fillNativeMultiSelect } from "./multi-select";
import { controlElementMap } from "./scanner";

function dispatchValueEvents(element: HTMLElement): void {
  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));
}

function dispatchInputEvent(element: HTMLElement): void {
  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
}

function setNativeValue(
  element: HTMLInputElement | HTMLTextAreaElement,
  value: string,
): void {
  const prototype =
    element instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : HTMLTextAreaElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  descriptor?.set?.call(element, value);
}

function setNativeChecked(element: HTMLInputElement, checked: boolean): void {
  const descriptor = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "checked",
  );
  descriptor?.set?.call(element, checked);
}

function compactText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function normalized(value: string): string {
  return compactText(value).toLowerCase();
}

function inputLabel(element: HTMLInputElement): string {
  return Array.from(element.labels ?? [])
    .map((label) => compactText(label.textContent))
    .filter(Boolean)
    .join(" ");
}

function radioCandidates(element: HTMLInputElement): HTMLInputElement[] {
  const root = element.getRootNode();
  const candidates =
    root instanceof Document || root instanceof ShadowRoot
      ? Array.from(root.querySelectorAll("input[type='radio']"))
      : [];
  if (!element.name) return [element];
  return candidates.filter(
    (candidate): candidate is HTMLInputElement =>
      candidate instanceof HTMLInputElement && candidate.name === element.name,
  );
}

function radioCandidateValues(element: HTMLInputElement): string[] {
  return [
    normalized(element.value),
    normalized(inputLabel(element)),
    normalized(element.getAttribute("aria-label") ?? ""),
  ].filter(Boolean);
}

function fillRadio(element: HTMLInputElement, value: string): boolean {
  const requested = normalized(value);
  const candidates = radioCandidates(element);
  let match = candidates.find((candidate) =>
    radioCandidateValues(candidate).includes(requested),
  );

  if (!match && ["true", "yes", "1", "checked"].includes(requested)) {
    match = candidates.find((candidate) =>
      radioCandidateValues(candidate).some((candidateValue) =>
        ["true", "yes", "1"].includes(candidateValue),
      ),
    );
  }
  if (!match && ["false", "no", "0", "unchecked"].includes(requested)) {
    match = candidates.find((candidate) =>
      radioCandidateValues(candidate).some((candidateValue) =>
        ["false", "no", "0"].includes(candidateValue),
      ),
    );
  }
  if (!match) return false;

  match.focus();
  setNativeChecked(match, true);
  dispatchValueEvents(match);
  return match.checked;
}

function fillCheckbox(element: HTMLInputElement, value: string): boolean {
  const requested = normalized(value);
  const truthy = ["true", "yes", "1", "checked"];
  const falsy = ["false", "no", "0", "unchecked"];
  if (!truthy.includes(requested) && !falsy.includes(requested)) {
    return false;
  }

  const shouldCheck = truthy.includes(requested);
  element.focus();
  setNativeChecked(element, shouldCheck);
  dispatchValueEvents(element);
  return element.checked === shouldCheck;
}

function controlledComboboxOptions(element: Element): HTMLElement[] {
  const root = element.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return [];
  const ids = [
    element.getAttribute("aria-controls"),
    element.getAttribute("aria-owns"),
  ]
    .filter((value): value is string => Boolean(value))
    .flatMap((value) => value.split(/\s+/))
    .filter(Boolean);
  const options: HTMLElement[] = [];
  for (const id of ids) {
    const container =
      root instanceof Document
        ? root.getElementById(id)
        : root.querySelector(`#${CSS.escape(id)}`);
    if (!container) continue;
    if (
      container instanceof HTMLElement &&
      container.getAttribute("role") === "option"
    ) {
      options.push(container);
    }
    for (const option of Array.from(
      container.querySelectorAll("[role='option']"),
    )) {
      if (option instanceof HTMLElement) options.push(option);
    }
  }
  return [...new Set(options)];
}

function comboboxOptionValues(option: HTMLElement): string[] {
  return [
    normalized(option.textContent ?? ""),
    normalized(option.getAttribute("aria-label") ?? ""),
    normalized(option.getAttribute("data-value") ?? ""),
  ].filter(Boolean);
}

function comboboxVerified(
  element: HTMLElement,
  option: HTMLElement,
  requested: string,
): boolean {
  if (
    element instanceof HTMLInputElement &&
    normalized(element.value) === requested
  ) {
    return true;
  }
  if (normalized(element.textContent ?? "") === requested) return true;
  if (option.getAttribute("aria-selected") === "true") return true;
  return (
    element.getAttribute("aria-activedescendant") === option.id &&
    Boolean(option.id)
  );
}

function fillCombobox(element: HTMLElement, value: string): boolean {
  const requested = normalized(value);
  if (!requested) return false;
  const originalValue =
    element instanceof HTMLInputElement ? element.value : null;
  element.focus();
  element.click();
  if (element instanceof HTMLInputElement) {
    setNativeValue(element, value);
    dispatchInputEvent(element);
  }

  const match = controlledComboboxOptions(element).find((option) =>
    comboboxOptionValues(option).includes(requested),
  );
  if (!match) {
    if (element instanceof HTMLInputElement && originalValue !== null) {
      setNativeValue(element, originalValue);
      dispatchInputEvent(element);
    }
    return false;
  }

  match.click();
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  const verified = comboboxVerified(element, match, requested);
  if (
    !verified &&
    element instanceof HTMLInputElement &&
    originalValue !== null
  ) {
    setNativeValue(element, originalValue);
    dispatchInputEvent(element);
  }
  return verified;
}

function fillElement(element: Element, value: string): boolean {
  if (
    element instanceof HTMLElement &&
    element.getAttribute("role") === "combobox"
  ) {
    return fillCombobox(element, value);
  }
  if (element instanceof HTMLInputElement) {
    if (
      ["file", "password", "hidden", "submit", "button", "reset"].includes(
        element.type,
      )
    ) {
      return false;
    }
    if (element.type === "radio") {
      return fillRadio(element, value);
    }
    if (element.type === "checkbox") {
      return fillCheckbox(element, value);
    }
    element.focus();
    setNativeValue(element, value);
    dispatchValueEvents(element);
    return element.value === value;
  }
  if (element instanceof HTMLTextAreaElement) {
    element.focus();
    setNativeValue(element, value);
    dispatchValueEvents(element);
    return element.value === value;
  }
  if (element instanceof HTMLSelectElement) {
    if (element.multiple) return fillNativeMultiSelect(element, value);
    const requested = normalized(value);
    const option = Array.from(element.options).find(
      (candidate) =>
        normalized(candidate.value) === requested ||
        normalized(candidate.text) === requested,
    );
    if (!option) return false;
    element.focus();
    element.value = option.value;
    dispatchValueEvents(element);
    return element.value === option.value;
  }
  if (element instanceof HTMLElement && element.isContentEditable) {
    element.focus();
    element.textContent = value;
    dispatchValueEvents(element);
    return element.textContent === value;
  }
  return false;
}

export function applyFillInstructions(
  instructions: FillInstruction[],
): FillResult[] {
  const elements = controlElementMap();
  return instructions.map((instruction) => {
    if (!instruction.approved) {
      return {
        controlId: instruction.controlId,
        status: "SKIPPED",
        reason: instruction.sensitive
          ? "Sensitive answer requires explicit approval"
          : "Answer was not approved",
      };
    }
    const element = elements.get(instruction.controlId);
    if (!element) {
      return {
        controlId: instruction.controlId,
        status: "FAILED",
        reason: "Visible control changed or is no longer available",
      };
    }
    const filled = fillElement(element, instruction.value);
    return {
      controlId: instruction.controlId,
      status: filled ? "FILLED" : "FAILED",
      reason: filled
        ? "Value applied, browser events dispatched, and DOM value verified"
        : "Control is unsupported or its value did not verify",
    };
  });
}
