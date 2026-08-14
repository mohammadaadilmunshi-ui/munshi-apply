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
) {
  const prototype =
    element instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : HTMLTextAreaElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  descriptor?.set?.call(element, value);
}

function fillElement(element: Element, value: string): boolean {
  if (element instanceof HTMLInputElement) {
    if (
      ["file", "password", "hidden", "submit", "button"].includes(element.type)
    ) {
      return false;
    }
    if (element.type === "checkbox" || element.type === "radio") {
      const shouldCheck = ["true", "yes", "1", "checked"].includes(
        value.trim().toLowerCase(),
      );
      const descriptor = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "checked",
      );
      descriptor?.set?.call(element, shouldCheck);
      dispatchValueEvents(element);
      return element.checked === shouldCheck;
    } else {
      setNativeValue(element, value);
      dispatchValueEvents(element);
      return element.value === value;
    }
  }
  if (element instanceof HTMLTextAreaElement) {
    setNativeValue(element, value);
    dispatchValueEvents(element);
    return element.value === value;
  }
  if (element instanceof HTMLSelectElement) {
    const normalized = value.trim().toLowerCase();
    const option = Array.from(element.options).find(
      (candidate) =>
        candidate.value.trim().toLowerCase() === normalized ||
        candidate.text.trim().toLowerCase() === normalized,
    );
    if (!option) return false;
    element.value = option.value;
    dispatchValueEvents(element);
    return element.value === option.value;
  }
  if (element instanceof HTMLElement && element.isContentEditable) {
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
        reason: "Answer was not approved",
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
    if (instruction.sensitive && !instruction.approved) {
      return {
        controlId: instruction.controlId,
        status: "SKIPPED",
        reason: "Sensitive answer requires explicit approval",
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
