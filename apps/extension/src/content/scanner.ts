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

function labelFor(element: Element): string {
  const ariaLabel = compactText(element.getAttribute("aria-label"));
  if (ariaLabel) return ariaLabel;

  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const value = labelledBy
      .split(/\s+/)
      .map((id) => compactText(document.getElementById(id)?.textContent))
      .filter(Boolean)
      .join(" ");
    if (value) return value;
  }

  if (element instanceof HTMLInputElement) {
    const labels = Array.from(element.labels ?? [])
      .map((label) => compactText(label.textContent))
      .filter(Boolean)
      .join(" ");
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
  return [];
}

function createControl(element: Element, index: number): Control | null {
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
  const signature = [
    element.tagName,
    element.id,
    name,
    label,
    placeholder,
    index,
  ].join("|");

  return {
    controlId: `ctl-${hash(signature)}`,
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

export function scanDocument(): ApplicationPage {
  const controls = Array.from(document.querySelectorAll(selector))
    .map(createControl)
    .filter((control): control is Control => control !== null);
  const questions = controls
    .map(createQuestion)
    .filter((question): question is Question => question !== null);
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

export function snapshotFingerprint(page: ApplicationPage): string {
  return hash(
    JSON.stringify({
      pageId: page.pageId,
      controls: page.controls,
      questions: page.questions,
    }),
  );
}
