function compact(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function normalized(value: string): string {
  return compact(value).toLocaleLowerCase("en-US");
}

function requestedValues(value: string): string[] | null {
  const trimmed = value.trim();
  if (!trimmed) return [];
  if (trimmed.startsWith("[")) {
    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (
        !Array.isArray(parsed) ||
        parsed.some((item) => typeof item !== "string")
      ) {
        return null;
      }
      return parsed.map((item) => compact(item));
    } catch {
      return null;
    }
  }
  return trimmed
    .split(/\r?\n|[;|,]/)
    .map(compact)
    .filter(Boolean);
}

export function fillNativeMultiSelect(
  element: HTMLSelectElement,
  value: string,
): boolean {
  if (!element.multiple) return false;
  const requested = requestedValues(value);
  if (!requested || requested.length === 0) return false;

  const previous = Array.from(element.options).map((option) => option.selected);
  const requestedNormalized = new Set(requested.map(normalized));
  const matches = new Set<HTMLOptionElement>();

  for (const requestedValue of requestedNormalized) {
    const match = Array.from(element.options).find(
      (option) =>
        normalized(option.value) === requestedValue ||
        normalized(option.text) === requestedValue,
    );
    if (!match) {
      Array.from(element.options).forEach((option, index) => {
        option.selected = previous[index] ?? false;
      });
      return false;
    }
    matches.add(match);
  }

  Array.from(element.options).forEach((option) => {
    option.selected = matches.has(option);
  });
  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));

  const selected = new Set(
    Array.from(element.selectedOptions).map((option) =>
      normalized(option.value || option.text),
    ),
  );
  const verified =
    selected.size === requestedNormalized.size &&
    [...requestedNormalized].every((item) => selected.has(item));

  if (!verified) {
    Array.from(element.options).forEach((option, index) => {
      option.selected = previous[index] ?? false;
    });
  }
  return verified;
}
