import {
  interactionContext,
  optionEquivalent,
  parseRequestedOptionValues,
} from "./adaptive";

export function fillNativeMultiSelect(
  element: HTMLSelectElement,
  value: string,
): boolean {
  if (!element.multiple || element.disabled) return false;
  const requested = parseRequestedOptionValues(value);
  if (!requested || requested.length === 0) return false;

  const previous = Array.from(element.options).map((option) => option.selected);
  const context = interactionContext(element);
  const matches = new Set<HTMLOptionElement>();

  for (const requestedValue of requested) {
    const candidates = Array.from(element.options).filter(
      (option) =>
        !option.disabled &&
        (optionEquivalent(option.value, requestedValue, context) ||
          optionEquivalent(option.text, requestedValue, context)),
    );
    if (candidates.length !== 1) {
      Array.from(element.options).forEach((option, index) => {
        option.selected = previous[index] ?? false;
      });
      return false;
    }
    matches.add(candidates[0]!);
  }

  if (matches.size !== requested.length) return false;
  Array.from(element.options).forEach((option) => {
    option.selected = matches.has(option);
  });
  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));

  const selected = Array.from(element.selectedOptions);
  const verified =
    selected.length === matches.size &&
    selected.every((option) => matches.has(option));
  if (!verified) {
    Array.from(element.options).forEach((option, index) => {
      option.selected = previous[index] ?? false;
    });
  }
  return verified;
}
