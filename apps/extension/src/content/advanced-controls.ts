import {
  compactText,
  interactionContext,
  optionEquivalent,
  parseRequestedOptionValues,
  waitForCondition,
  type AdaptiveTiming,
} from "./adaptive";

function setNativeInputValue(element: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  if (setter) setter.call(element, value);
  else element.value = value;
}

function dispatchValueEvents(element: HTMLElement): void {
  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));
}

function leapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function validDateParts(year: number, month: number, day: number): boolean {
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1) {
    return false;
  }
  const days = [31, leapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= days[month - 1]!;
}

function validMonth(value: string): boolean {
  const match = value.match(/^(\d{4})-(\d{2})$/);
  return Boolean(match && Number(match[1]) >= 1 && Number(match[2]) >= 1 && Number(match[2]) <= 12);
}

function validTime(value: string): boolean {
  const match = value.match(/^(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) return false;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  const second = match[3] === undefined ? 0 : Number(match[3]);
  return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 && second >= 0 && second <= 59;
}

function validDateTimeLocal(value: string): boolean {
  const match = value.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/,
  );
  if (!match) return false;
  return (
    validDateParts(Number(match[1]), Number(match[2]), Number(match[3])) &&
    validTime(`${match[4]}:${match[5]}${match[6] === undefined ? "" : `:${match[6]}`}`)
  );
}

function isoWeeksInYear(year: number): number {
  const december28 = new Date(Date.UTC(year, 11, 28));
  const day = december28.getUTCDay() || 7;
  const thursday = new Date(december28);
  thursday.setUTCDate(december28.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
  return Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
}

function validWeek(value: string): boolean {
  const match = value.match(/^(\d{4})-W(\d{2})$/);
  if (!match) return false;
  const year = Number(match[1]);
  const week = Number(match[2]);
  return year >= 1 && year <= 9999 && week >= 1 && week <= isoWeeksInYear(year);
}

export type StrictTemporalKind = "month" | "time" | "datetime-local" | "week";

export function fillStrictTemporalInput(
  element: HTMLInputElement,
  value: string,
): boolean | null {
  const type = element.type as StrictTemporalKind;
  if (!["month", "time", "datetime-local", "week"].includes(type)) return null;
  if (element.disabled || element.readOnly) return false;
  const requested = value.trim();
  const valid =
    (type === "month" && validMonth(requested)) ||
    (type === "time" && validTime(requested)) ||
    (type === "datetime-local" && validDateTimeLocal(requested)) ||
    (type === "week" && validWeek(requested));
  if (!valid) return false;

  const original = element.value;
  element.focus();
  setNativeInputValue(element, requested);
  dispatchValueEvents(element);
  const verified = element.value === requested && element.validity.valid;
  if (!verified) {
    setNativeInputValue(element, original);
    dispatchValueEvents(element);
  }
  return verified;
}

function rootFor(element: Element): Document | ShadowRoot {
  const root = element.getRootNode();
  return root instanceof ShadowRoot ? root : document;
}

function controlledContainers(element: HTMLElement): HTMLElement[] {
  const ids = [element.getAttribute("aria-controls"), element.getAttribute("aria-owns")]
    .filter((value): value is string => Boolean(value))
    .flatMap((value) => value.split(/\s+/))
    .filter(Boolean);
  const roots: Array<Document | ShadowRoot> = [rootFor(element)];
  if (!roots.includes(document)) roots.push(document);
  const containers: HTMLElement[] = [];
  if (element.getAttribute("aria-multiselectable") === "true") containers.push(element);
  for (const id of ids) {
    for (const root of roots) {
      const candidate =
        root instanceof Document
          ? root.getElementById(id)
          : root.querySelector(`#${CSS.escape(id)}`);
      if (candidate instanceof HTMLElement) containers.push(candidate);
    }
  }
  return [...new Set(containers)];
}

function available(element: HTMLElement): boolean {
  return (
    !element.hidden &&
    element.getAttribute("aria-hidden") !== "true" &&
    element.getAttribute("aria-disabled") !== "true" &&
    !element.hasAttribute("disabled")
  );
}

function selected(element: HTMLElement): boolean {
  return (
    element.getAttribute("aria-selected") === "true" ||
    element.getAttribute("aria-checked") === "true"
  );
}

function optionValues(element: HTMLElement): string[] {
  return [
    compactText(element.textContent),
    compactText(element.getAttribute("aria-label")),
    compactText(element.getAttribute("data-value")),
    compactText(element.getAttribute("value")),
  ].filter(Boolean);
}

function optionElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll("[role='option'], [role='treeitem']"),
  ).filter((item): item is HTMLElement => item instanceof HTMLElement && available(item));
}

function exactTargets(
  container: HTMLElement,
  requested: readonly string[],
  context: string,
): HTMLElement[] | null {
  const options = optionElements(container);
  const targets: HTMLElement[] = [];
  for (const requestedValue of requested) {
    const matches = options.filter((option) =>
      optionValues(option).some((candidate) =>
        optionEquivalent(candidate, requestedValue, context),
      ),
    );
    if (matches.length !== 1) return null;
    if (targets.includes(matches[0]!)) return null;
    targets.push(matches[0]!);
  }
  return targets;
}

async function restoreSelection(
  options: readonly HTMLElement[],
  originals: ReadonlyMap<HTMLElement, boolean>,
  timing: AdaptiveTiming,
): Promise<void> {
  for (const option of options) {
    const original = originals.get(option) ?? false;
    if (selected(option) === original) continue;
    option.click();
    await waitForCondition(
      () => selected(option) === original,
      timing.verificationTimeoutMs,
      timing.pollIntervalMs,
    );
  }
}

export function isAriaMultiSelectControl(element: Element): boolean {
  if (!(element instanceof HTMLElement)) return false;
  if (element.getAttribute("aria-multiselectable") === "true") return true;
  return controlledContainers(element).some(
    (container) => container.getAttribute("aria-multiselectable") === "true",
  );
}

export async function fillAriaMultiSelectControl(
  element: HTMLElement,
  value: string,
  timing: AdaptiveTiming,
): Promise<boolean | null> {
  if (!isAriaMultiSelectControl(element)) return null;
  const requested = parseRequestedOptionValues(value);
  if (!requested || requested.length === 0) return false;
  if (new Set(requested.map((item) => item.toLocaleLowerCase("en-US"))).size !== requested.length) {
    return false;
  }

  element.focus();
  if (element.getAttribute("aria-expanded") === "false") element.click();
  const deadline = Date.now() + timing.optionTimeoutMs;
  let container: HTMLElement | null = null;
  let targets: HTMLElement[] | null = null;
  const context = interactionContext(element);
  while (Date.now() <= deadline) {
    const candidates = controlledContainers(element).filter(
      (item) => item.getAttribute("aria-multiselectable") === "true",
    );
    if (candidates.length > 1) return false;
    if (candidates.length === 1) {
      const found = exactTargets(candidates[0]!, requested, context);
      if (found) {
        container = candidates[0]!;
        targets = found;
        break;
      }
    }
    await new Promise((resolve) => window.setTimeout(resolve, timing.pollIntervalMs));
  }
  if (!container || !targets) return false;

  const options = optionElements(container);
  const originals = new Map(options.map((option) => [option, selected(option)] as const));
  const targetSet = new Set(targets);
  for (const option of options) {
    const desired = targetSet.has(option);
    if (selected(option) === desired) continue;
    option.click();
    const changed = await waitForCondition(
      () => selected(option) === desired,
      timing.verificationTimeoutMs,
      timing.pollIntervalMs,
    );
    if (!changed) {
      await restoreSelection(options, originals, timing);
      return false;
    }
  }

  const verified = options.every((option) => selected(option) === targetSet.has(option));
  if (!verified) await restoreSelection(options, originals, timing);
  return verified;
}
