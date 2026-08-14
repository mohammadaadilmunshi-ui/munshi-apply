import type { FillInstruction, FillResult } from "@munshi-apply/contracts";
import { fillNativeMultiSelect } from "./multi-select";
import { controlElementMap } from "./scanner";

export type FillInteractionOptions = {
  optionTimeoutMs?: number;
  pollIntervalMs?: number;
};

const DEFAULT_OPTION_TIMEOUT_MS = 1_200;
const DEFAULT_POLL_INTERVAL_MS = 25;

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

function canonicalDate(value: string): string | null {
  const requested = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(requested)) return null;
  const parsed = new Date(`${requested}T00:00:00.000Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString().slice(0, 10) === requested ? requested : null;
}

function fillDate(element: HTMLInputElement, value: string): boolean {
  const requested = canonicalDate(value);
  if (!requested) return false;
  element.focus();
  setNativeValue(element, requested);
  dispatchValueEvents(element);
  return element.value === requested;
}

function collectOpenShadowRoots(root: Document | ShadowRoot): ShadowRoot[] {
  const roots: ShadowRoot[] = [];
  for (const candidate of Array.from(root.querySelectorAll("*"))) {
    if (!(candidate instanceof HTMLElement) || !candidate.shadowRoot) continue;
    roots.push(candidate.shadowRoot);
    roots.push(...collectOpenShadowRoots(candidate.shadowRoot));
  }
  return roots;
}

function optionSearchRoots(element: Element): Array<Document | ShadowRoot> {
  const roots: Array<Document | ShadowRoot> = [];
  const ownRoot = element.getRootNode();
  if (ownRoot instanceof Document || ownRoot instanceof ShadowRoot) {
    roots.push(ownRoot);
  }
  if (!roots.includes(document)) roots.push(document);
  for (const shadowRoot of collectOpenShadowRoots(document)) {
    if (!roots.includes(shadowRoot)) roots.push(shadowRoot);
  }
  return roots;
}

function elementById(root: Document | ShadowRoot, id: string): Element | null {
  return root instanceof Document
    ? root.getElementById(id)
    : root.querySelector(`#${CSS.escape(id)}`);
}

function optionsInside(container: Element): HTMLElement[] {
  const options: HTMLElement[] = [];
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
  return options;
}

function controlledComboboxOptions(element: Element): HTMLElement[] {
  const ids = [
    element.getAttribute("aria-controls"),
    element.getAttribute("aria-owns"),
  ]
    .filter((value): value is string => Boolean(value))
    .flatMap((value) => value.split(/\s+/))
    .filter(Boolean);
  const options: HTMLElement[] = [];
  for (const root of optionSearchRoots(element)) {
    for (const id of ids) {
      const container = elementById(root, id);
      if (container) options.push(...optionsInside(container));
    }
  }
  return [...new Set(options)];
}

function portaledComboboxOptions(element: Element): HTMLElement[] {
  const options: HTMLElement[] = [];
  for (const root of optionSearchRoots(element)) {
    for (const option of Array.from(root.querySelectorAll("[role='option']"))) {
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

function optionAvailable(option: HTMLElement): boolean {
  return (
    !option.hidden &&
    option.getAttribute("aria-hidden") !== "true" &&
    option.getAttribute("aria-disabled") !== "true" &&
    !option.hasAttribute("disabled")
  );
}

type ExactOptionResult =
  | { status: "FOUND"; option: HTMLElement }
  | { status: "WAIT" }
  | { status: "AMBIGUOUS" };

function exactComboboxOption(
  element: Element,
  requested: string,
): ExactOptionResult {
  const controlled = controlledComboboxOptions(element).filter(
    (option) =>
      optionAvailable(option) &&
      comboboxOptionValues(option).includes(requested),
  );
  if (controlled.length === 1) {
    return { status: "FOUND", option: controlled[0]! };
  }
  if (controlled.length > 1) return { status: "AMBIGUOUS" };

  const portaled = portaledComboboxOptions(element).filter(
    (option) =>
      optionAvailable(option) &&
      comboboxOptionValues(option).includes(requested),
  );
  if (portaled.length === 1) {
    return { status: "FOUND", option: portaled[0]! };
  }
  return portaled.length > 1 ? { status: "AMBIGUOUS" } : { status: "WAIT" };
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

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForExactComboboxOption(
  element: HTMLElement,
  requested: string,
  timeoutMilliseconds: number,
  pollIntervalMilliseconds: number,
): Promise<HTMLElement | null> {
  const deadline = Date.now() + timeoutMilliseconds;
  while (Date.now() <= deadline) {
    const result = exactComboboxOption(element, requested);
    if (result.status === "FOUND") return result.option;
    if (result.status === "AMBIGUOUS") return null;
    await delay(pollIntervalMilliseconds);
  }
  return null;
}

async function waitForComboboxVerification(
  element: HTMLElement,
  option: HTMLElement,
  requested: string,
  timeoutMilliseconds: number,
  pollIntervalMilliseconds: number,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMilliseconds;
  while (Date.now() <= deadline) {
    if (comboboxVerified(element, option, requested)) return true;
    await delay(pollIntervalMilliseconds);
  }
  return false;
}

async function fillCombobox(
  element: HTMLElement,
  value: string,
  options: Required<FillInteractionOptions>,
): Promise<boolean> {
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

  const match = await waitForExactComboboxOption(
    element,
    requested,
    options.optionTimeoutMs,
    options.pollIntervalMs,
  );
  if (!match) {
    if (element instanceof HTMLInputElement && originalValue !== null) {
      setNativeValue(element, originalValue);
      dispatchValueEvents(element);
    }
    return false;
  }

  match.click();
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  const verified = await waitForComboboxVerification(
    element,
    match,
    requested,
    Math.min(options.optionTimeoutMs, 500),
    options.pollIntervalMs,
  );
  if (!verified && element instanceof HTMLInputElement && originalValue !== null) {
    setNativeValue(element, originalValue);
    dispatchValueEvents(element);
  }
  return verified;
}

async function fillElement(
  element: Element,
  value: string,
  options: Required<FillInteractionOptions>,
): Promise<boolean> {
  if (
    element instanceof HTMLElement &&
    element.getAttribute("role") === "combobox"
  ) {
    return fillCombobox(element, value, options);
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
    if (element.type === "date") {
      return fillDate(element, value);
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

export async function applyFillInstructions(
  instructions: FillInstruction[],
  interactionOptions: FillInteractionOptions = {},
): Promise<FillResult[]> {
  const elements = controlElementMap();
  const options: Required<FillInteractionOptions> = {
    optionTimeoutMs:
      interactionOptions.optionTimeoutMs ?? DEFAULT_OPTION_TIMEOUT_MS,
    pollIntervalMs:
      interactionOptions.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,
  };
  const results: FillResult[] = [];

  for (const instruction of instructions) {
    if (!instruction.approved) {
      results.push({
        controlId: instruction.controlId,
        status: "SKIPPED",
        reason: instruction.sensitive
          ? "Sensitive answer requires explicit approval"
          : "Answer was not approved",
      });
      continue;
    }
    const element = elements.get(instruction.controlId);
    if (!element) {
      results.push({
        controlId: instruction.controlId,
        status: "FAILED",
        reason: "Visible control changed or is no longer available",
      });
      continue;
    }

    let filled = false;
    try {
      filled = await fillElement(element, instruction.value, options);
    } catch {
      filled = false;
    }
    results.push({
      controlId: instruction.controlId,
      status: filled ? "FILLED" : "FAILED",
      reason: filled
        ? "Value applied, browser events dispatched, and DOM value verified"
        : "Control is unsupported, ambiguous, timed out, or its value did not verify",
    });
  }

  return results;
}
