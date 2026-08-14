import type {
  ApplicationPage,
  Control,
  ControlKind,
  Question,
} from "@munshi-apply/contracts";
import { classifyQuestion } from "@munshi-apply/semantic-engine";

const selector = [
  "input",
  "select",
  "textarea",
  "button",
  "[role='combobox']",
  "[contenteditable='true']",
].join(",");

function collectInteractiveElements(root: Document | ShadowRoot): Element[] {
  const collected: Element[] = [];
  for (const element of Array.from(root.querySelectorAll(selector))) {
    collected.push(element);
    if (element.shadowRoot) {
      collected.push(...collectInteractiveElements(element.shadowRoot));
    }
  }

  for (const host of Array.from(root.querySelectorAll("*"))) {
    if (
      host.shadowRoot &&
      !collected.some((element) => element.getRootNode() === host.shadowRoot)
    ) {
      collected.push(...collectInteractiveElements(host.shadowRoot));
    }
  }
  return collected;
}

function compactText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function isVisible(element: Element): boolean {
  if (!(element instanceof HTMLElement)) return false;
  const style = window.getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  if (
    element.hidden ||
    element.getAttribute("aria-hidden") === "true" ||
    style.display === "none" ||
    style.visibility === "hidden" ||
    style.opacity === "0" ||
    rect.width <= 0 ||
    rect.height <= 0
  ) {
    return false;
  }
  const explicitlyPositioned =
    style.position === "absolute" || style.position === "fixed";
  return !explicitlyPositioned || (rect.right > 0 && rect.bottom > 0);
}

function hash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function inputLabel(element: HTMLInputElement): string {
  return Array.from(element.labels ?? [])
    .map((label) => compactText(label.textContent))
    .filter(Boolean)
    .join(" ");
}

function radioGroup(element: HTMLInputElement): HTMLInputElement[] {
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

function radioOptionLabel(element: HTMLInputElement): string {
  return (
    inputLabel(element) ||
    compactText(element.getAttribute("aria-label")) ||
    compactText(element.value)
  );
}

function groupLegend(element: Element): string {
  const fieldset = element.closest("fieldset");
  return compactText(fieldset?.querySelector(":scope > legend")?.textContent);
}

function labelFor(element: Element): string {
  const ariaLabel = compactText(element.getAttribute("aria-label"));
  if (ariaLabel) return ariaLabel;

  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const root = element.getRootNode();
    const value = labelledBy
      .split(/\s+/)
      .map((id) => {
        const labelledElement =
          root instanceof Document
            ? root.getElementById(id)
            : root instanceof ShadowRoot
              ? root.querySelector(`#${CSS.escape(id)}`)
              : null;
        return compactText(labelledElement?.textContent);
      })
      .filter(Boolean)
      .join(" ");
    if (value) return value;
  }

  if (element instanceof HTMLInputElement) {
    if (element.type === "radio") {
      const legend = groupLegend(element);
      if (legend) return legend;
    }
    const labels = inputLabel(element);
    if (labels) return labels;
  }

  if (
    element instanceof HTMLSelectElement ||
    element instanceof HTMLTextAreaElement
  ) {
    const labels = Array.from(element.labels)
      .map((label) => compactText(label.textContent))
      .filter(Boolean)
      .join(" ");
    if (labels) return labels;
  }

  const container = element.closest("fieldset, [role='group'], .form-group");
  const legend = compactText(container?.querySelector("legend")?.textContent);
  return legend;
}

function kindFor(element: Element): ControlKind {
  if (element.getAttribute("role") === "combobox") return "COMBOBOX";
  if (element instanceof HTMLTextAreaElement) return "TEXTAREA";
  if (element instanceof HTMLSelectElement) return "SELECT";
  if (element instanceof HTMLButtonElement) return "BUTTON";
  if (element instanceof HTMLInputElement) {
    const mapping: Partial<Record<string, ControlKind>> = {
      checkbox: "CHECKBOX",
      date: "DATE",
      email: "EMAIL",
      file: "FILE",
      number: "NUMBER",
      radio: "RADIO",
      tel: "TEL",
      text: "TEXT",
    };
    return mapping[element.type] ?? "UNKNOWN";
  }
  return element.getAttribute("contenteditable") === "true"
    ? "TEXTAREA"
    : "UNKNOWN";
}

function optionsFor(element: Element): string[] {
  if (element instanceof HTMLSelectElement) {
    return Array.from(element.options).map((option) =>
      compactText(option.text),
    );
  }
  if (element instanceof HTMLInputElement && element.type === "radio") {
    return radioGroup(element).map(radioOptionLabel).filter(Boolean);
  }
  return [];
}

function stableControlSignature(element: Element): string {
  const url = new URL(window.location.href);
  const type = element instanceof HTMLInputElement ? element.type : "";
  const optionValue =
    element instanceof HTMLInputElement &&
    (element.type === "radio" || element.type === "checkbox")
      ? element.value
      : "";
  return [
    url.origin,
    url.pathname,
    element.tagName,
    element.id,
    compactText(element.getAttribute("name")),
    type,
    labelFor(element),
    compactText(element.getAttribute("placeholder")),
    compactText(element.getAttribute("aria-label")),
    compactText(element.getAttribute("autocomplete")),
    compactText(optionValue),
  ].join("|");
}

function createControl(element: Element): Control | null {
  if (!isVisible(element)) return null;
  if (
    element instanceof HTMLInputElement &&
    ["hidden", "password"].includes(element.type)
  ) {
    return null;
  }

  const name = compactText(element.getAttribute("name"));
  const label = labelFor(element);
  const placeholder = compactText(element.getAttribute("placeholder"));
  const ariaLabel = compactText(element.getAttribute("aria-label"));

  return {
    controlId: `ctl-${hash(stableControlSignature(element))}`,
    frameId: 0,
    kind: kindFor(element),
    tagName: element.tagName.toLowerCase(),
    name,
    label,
    placeholder,
    ariaLabel,
    required:
      element.hasAttribute("required") ||
      element.getAttribute("aria-required") === "true",
    disabled:
      ("disabled" in element &&
        Boolean((element as HTMLInputElement).disabled)) ||
      element.getAttribute("aria-disabled") === "true",
    visible: true,
    options: optionsFor(element),
  };
}

type ControlEntry = { element: Element; control: Control };

function scanControlEntries(): ControlEntry[] {
  const duplicateCounts = new Map<string, number>();
  const entries: ControlEntry[] = [];
  for (const element of collectInteractiveElements(document)) {
    const control = createControl(element);
    if (!control) continue;
    const count = duplicateCounts.get(control.controlId) ?? 0;
    duplicateCounts.set(control.controlId, count + 1);
    entries.push({
      element,
      control:
        count === 0
          ? control
          : { ...control, controlId: `${control.controlId}-${count + 1}` },
    });
  }
  return entries;
}

function createQuestion(control: Control): Question | null {
  if (control.kind === "BUTTON") return null;
  const rawText =
    control.label || control.ariaLabel || control.placeholder || control.name;
  if (!rawText) return null;
  const classification = classifyQuestion(rawText);
  return {
    questionId: `q-${control.controlId}`,
    controlId: control.controlId,
    rawText,
    semanticType: classification.semanticType,
    confidence: classification.confidence,
    sensitive: classification.sensitive,
    requiresReview: classification.requiresReview,
  };
}

function questionIdentity(entry: ControlEntry, question: Question): string {
  if (
    entry.control.kind === "RADIO" &&
    entry.element instanceof HTMLInputElement &&
    entry.element.name
  ) {
    return `radio|${entry.element.name}|${question.rawText}`;
  }
  return entry.control.controlId;
}

export function scanDocument(): ApplicationPage {
  const entries = scanControlEntries();
  const controls = entries.map((entry) => entry.control);
  const questions: Question[] = [];
  const seenQuestions = new Set<string>();
  for (const entry of entries) {
    const question = createQuestion(entry.control);
    if (!question) continue;
    const identity = questionIdentity(entry, question);
    if (seenQuestions.has(identity)) continue;
    seenQuestions.add(identity);
    questions.push(question);
  }
  const url = new URL(window.location.href);
  const pageSignature = `${url.origin}${url.pathname}|${document.title}`;

  return {
    pageId: `page-${hash(pageSignature)}`,
    tabId: -1,
    frameId: 0,
    documentId: `doc-${hash(pageSignature)}`,
    url: url.href,
    title: document.title,
    observedAt: new Date().toISOString(),
    controls,
    questions,
  };
}

export function controlElementMap(): Map<string, Element> {
  return new Map(
    scanControlEntries().map((entry) => [
      entry.control.controlId,
      entry.element,
    ]),
  );
}

export function snapshotFingerprint(page: ApplicationPage): string {
  return hash(
    JSON.stringify({
      pageId: page.pageId,
      controls: page.controls,
      questions: page.questions,
    }),
  );
}
