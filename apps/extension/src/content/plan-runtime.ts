// Reuse the production scanner, classifier, fill and navigation implementations.
// This bundle exposes mechanics only; native orchestration owns execution policy.
import { applyFillInstructions } from "./fill";
import { applyNavigationAction } from "./navigation";
import { resolveControlElement, scanDocument } from "./scanner";

export { applyFillInstructions, applyNavigationAction, scanDocument };

export function element(controlId: string): Element | null {
  return resolveControlElement(controlId)?.element ?? null;
}


// WORKDAY_SELECTED_PROMPT_VERIFIER_V2
// Workday search/prompt inputs are query surfaces, not sources of truth. Typed
// text is never treated as committed unless Workday exposes a selected item or
// an explicit backing value for the component.
function isWorkdayPromptControl(node: Element | null): node is HTMLInputElement {
  if (!(node instanceof HTMLInputElement)) return false;

  const compact = (value: unknown) =>
    String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  const host = compact(window.location.hostname);
  const role = compact(node.getAttribute("role"));
  const popup = compact(node.getAttribute("aria-haspopup"));
  const autocomplete = compact(node.getAttribute("aria-autocomplete"));
  const descriptor = compact([
    node.getAttribute("data-automation-id"),
    node.parentElement?.getAttribute("data-automation-id"),
    node.closest("[data-automation-id]")?.getAttribute("data-automation-id"),
  ].filter(Boolean).join(" "));

  const promptShape =
    role === "combobox"
    || ["listbox", "tree", "grid"].includes(popup)
    || ["list", "both"].includes(autocomplete)
    || /(?:^|\b)(prompt|search|lookup|typeahead)(?:\b|$)/.test(descriptor);

  const workdaySurface =
    host.includes("myworkdayjobs")
    || host.includes("myworkdaysite")
    || Boolean(
      node.closest(
        '[data-automation-id*="prompt" i],'
        + '[data-automation-id*="search" i],'
        + '[data-automation-id*="lookup" i]',
      ),
    )
    || Boolean(
      document.querySelector(
        '[data-automation-id="promptOption"],'
        + '[data-automation-id^="selectedItem"]',
      ),
    );

  return promptShape && workdaySurface;
}

function singleChoiceCheckboxSelectedValue(
  node: Element | null,
  options: readonly string[] | undefined,
): string {
  if (
    !(node instanceof HTMLInputElement)
    || node.type !== "checkbox"
    || !node.name
    || !Array.isArray(options)
    || options.length < 2
  ) {
    return "";
  }
  const root = node.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return "";
  const candidates = Array.from(
    root.querySelectorAll("input[type='checkbox']"),
  ).filter(
    (candidate): candidate is HTMLInputElement =>
      candidate instanceof HTMLInputElement
      && candidate.name === node.name
      && candidate.checked,
  );
  if (candidates.length !== 1) return "";
  const selected = candidates[0]!;
  const label = Array.from(selected.labels ?? [])
    .map((item) => String(item.textContent || "").replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join(" ");
  const fallback =
    selected.getAttribute("aria-label")
    || selected.value
    || "";
  const value = String(label || fallback).replace(/\s+/g, " ").trim();
  return options.some(
    (option) =>
      String(option || "").replace(/\s+/g, " ").trim().toLowerCase()
      === value.toLowerCase(),
  )
    ? value
    : "";
}

function workdaySelectedPromptValue(node: Element | null): string {
  if (!isWorkdayPromptControl(node)) return "";

  const compact = (value: unknown) =>
    String(value || "").replace(/\s+/g, " ").trim();
  const direct = compact(
    node.getAttribute("data-value")
    || node.getAttribute("aria-valuetext")
    || "",
  );
  if (direct) return direct;

  const promptValue = (item: Element) => {
    const prompt = item.matches('[data-automation-id="promptOption"]')
      ? item
      : item.querySelector('[data-automation-id="promptOption"]');
    const candidate = prompt || item;
    return compact(
      candidate.getAttribute("data-automation-label")
      || candidate.getAttribute("aria-label")
      || candidate.getAttribute("title")
      || candidate.textContent
      || "",
    );
  };

  const scopes: Element[] = [];
  let scope: Element | null = node.parentElement;
  for (let depth = 0; scope && depth < 10; depth += 1, scope = scope.parentElement) {
    scopes.push(scope);
  }

  for (const candidateScope of scopes) {
    const selected = Array.from(
      candidateScope.querySelectorAll(
        '[data-automation-id^="selectedItem"],'
        + '[role="option"][aria-selected="true"],'
        + '[data-automation-id="promptOption"][aria-selected="true"]',
      ),
    );
    if (!selected.length) continue;
    const values = [...new Set(selected.map(promptValue).filter(Boolean))];
    if (values.length === 1) return values[0]!;
    if (values.length > 1) return "";
  }
  return "";
}

type BrowserSensitivityClass =
  | "NORMAL"
  | "PROTECTED"
  | "SELF_ID"
  | "POST_OFFER";

const selfIdSemantics = new Set([
  "GENDER",
  "RACE_ETHNICITY",
  "HISPANIC_LATINO",
  "VETERAN_STATUS",
  "PROTECTED_VETERAN_STATUS",
  "DISABILITY_STATUS",
  "EEO_SELF_ID",
]);

const postOfferSemantics = new Set(["EMPLOYEE_ID"]);

const protectedSemantics = new Set([
  "WORK_AUTHORIZATION_CURRENT",
  "WORK_LOCATION_ELIGIBILITY",
  "AGE_18_PLUS",
  "SPONSORSHIP_CURRENT",
  "SPONSORSHIP_FUTURE",
  "IMMIGRATION_ASSISTANCE",
  "SECURITY_CLEARANCE",
]);

function browserSensitivityClass(
  semanticType: string,
  sensitive: boolean,
): BrowserSensitivityClass {
  if (selfIdSemantics.has(semanticType)) return "SELF_ID";
  if (postOfferSemantics.has(semanticType)) return "POST_OFFER";
  if (protectedSemantics.has(semanticType) || sensitive) return "PROTECTED";
  return "NORMAL";
}

export async function describeForm() {
  const page = scanDocument();
  const fields = await Promise.all(
    page.questions.map(async (question) => {
      const resolved = resolveControlElement(question.controlId);
      const control = resolved?.control;
      const node: Element | null = resolved?.element ?? null;
      const workdayPrompt = isWorkdayPromptControl(node);
      const workdaySelectedValue = workdaySelectedPromptValue(node);
      const sensitivityClass = browserSensitivityClass(
        question.semanticType,
        question.sensitive,
      );
      let value = "";
      if (node instanceof HTMLInputElement) {
        if (workdayPrompt) {
          value = workdaySelectedValue;
        } else if (node.type === "checkbox") {
          value =
            singleChoiceCheckboxSelectedValue(node, control?.options)
            || String(node.checked);
        } else {
          value = node.type === "radio"
            ? String(node.checked)
            : node.value;
        }
      } else if (
        node instanceof HTMLSelectElement ||
        node instanceof HTMLTextAreaElement
      ) {
        value = node.value;
      }
      const digest = await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(value),
      );
      const valueDigest = Array.from(new Uint8Array(digest), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join("");
      return {
        control_id: question.controlId,
        question_key: control?.name || question.questionId,
        question: question.rawText,
        semantic_type: question.semanticType,
        semantic_confidence: question.semanticConfidence ?? question.confidence,
        question_observation: {
          raw_question: question.rawText,
          label: question.label ?? control?.label ?? "",
          section_heading: question.sectionHeading ?? "",
          nearby_text: question.nearbyText ?? "",
          placeholder: question.placeholder ?? control?.placeholder ?? "",
          name: question.fieldName ?? control?.name ?? "",
          id: question.elementId ?? "",
          autocomplete: question.autocomplete ?? control?.autocomplete ?? "",
          input_type: question.inputType ?? control?.inputType ?? "",
          role: question.role ?? control?.role ?? "",
          options: question.options ?? control?.options ?? [],
          apply_semantic_type: question.semanticType,
          apply_semantic_confidence:
            question.semanticConfidence ?? question.confidence,
          control_id: question.controlId,
          page_id: page.pageId,
          repeat_group: question.repeatGroupId ?? null,
          repeat_index: question.repeatIndex ?? null,
          previous_labels: question.previousLabels ?? [],
          next_labels: question.nextLabels ?? [],
          option_signature: question.optionSignature ?? "",
          input_constraints: question.inputConstraints ?? {},
          logical_field_fingerprint_inputs:
            question.logicalFieldFingerprintInputs ?? null,
        },
        sensitivity_class: sensitivityClass,
        display_value:
          sensitivityClass === "NORMAL" ? value : "[protected value]",
        value_digest: valueDigest,
        required: control?.required ?? false,
        satisfied:
          (control?.invalid ?? false)
            ? false
            : workdayPrompt
              ? Boolean(workdaySelectedValue)
              : Boolean(control?.satisfied || value),
        invalid: control?.invalid ?? false,
      };
    }),
  );
  return { page, fields };
}
