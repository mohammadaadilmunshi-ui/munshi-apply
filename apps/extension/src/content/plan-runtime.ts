// Reuse the production scanner, classifier, fill and navigation implementations.
// This bundle exposes mechanics only; native orchestration owns execution policy.
import { applyFillInstructions } from "./fill";
import { applyNavigationAction } from "./navigation";
import { resolveControlElement, scanDocument } from "./scanner";

export { applyFillInstructions, applyNavigationAction, scanDocument };

export function element(controlId: string): Element | null {
  return resolveControlElement(controlId)?.element ?? null;
}


// WORKDAY_SELECTED_PROMPT_VERIFIER_V1
function workdaySelectedPromptValue(node: Element | null): string {
  if (!(node instanceof HTMLInputElement)) return "";
  if (!String(node.id || "").toLowerCase().includes("source--source")) return "";

  const compact = (value: unknown) =>
    String(value || "").replace(/\s+/g, " ").trim();
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

  let scope: Element | null = node.parentElement;
  for (let depth = 0; scope && depth < 9; depth += 1, scope = scope.parentElement) {
    const selected = Array.from(
      scope.querySelectorAll('[data-automation-id^="selectedItem"]'),
    );
    if (!selected.length) continue;
    const values = [...new Set(selected.map(promptValue).filter(Boolean))];
    return values.length === 1 ? values[0]! : "";
  }
  return "";
}

export async function describeForm() {
  const page = scanDocument();
  const fields = await Promise.all(
    page.questions.map(async (question) => {
      const resolved = resolveControlElement(question.controlId);
      const control = resolved?.control;
      const node = resolved?.element;
      const workdaySelectedValue = workdaySelectedPromptValue(node);
      let value = "";
      if (node instanceof HTMLInputElement) {
        value = ["checkbox", "radio"].includes(node.type)
          ? String(node.checked)
          : node.value;
      } else if (
        node instanceof HTMLSelectElement ||
        node instanceof HTMLTextAreaElement
      ) {
        value = node.value;
      }
      if (!value && workdaySelectedValue) value = workdaySelectedValue;
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
        sensitivity_class: question.sensitive ? "PROTECTED" : "NORMAL",
        display_value: question.sensitive ? "[protected value]" : value,
        value_digest: valueDigest,
        required: control?.required ?? false,
        satisfied:
          (control?.invalid ?? false)
            ? false
            : Boolean(control?.satisfied || value || workdaySelectedValue),
        invalid: control?.invalid ?? false,
      };
    }),
  );
  return { page, fields };
}
