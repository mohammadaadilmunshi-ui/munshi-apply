import type { FillInstruction, FillResult } from "@munshi-apply/contracts";
import { controlElementMap } from "./scanner";

function dispatchValueEvents(element: HTMLElement): void {
  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));
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

function fillElement(element: Element, value: string): boolean {
  if (element instanceof HTMLInputElement) {
    if (
      ["file", "password", "hidden", "submit", "button"].includes(element.type)
    ) {
      return false;
    }
    if (element.type === "radio") {
      return fillRadio(element, value);
    }
    if (element.type === "checkbox") {
      const shouldCheck = ["true", "yes", "1", "checked"].includes(
        normalized(value),
      );
      element.focus();
      setNativeChecked(element, shouldCheck);
      dispatchValueEvents(element);
      return element.checked === shouldCheck;
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
