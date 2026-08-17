const APPLICATION_RELEVANT_SELECTOR = [
  "form",
  "input",
  "select",
  "textarea",
  "button",
  "iframe",
  "[contenteditable='true']",
  "[role='button']",
  "[role='checkbox']",
  "[role='combobox']",
  "[role='listbox']",
  "[role='option']",
  "[role='radio']",
  "[role='switch']",
  "[aria-invalid='true']",
  "[aria-required='true']",
].join(",");

function elementTouchesApplication(element: Element): boolean {
  return (
    element.matches(APPLICATION_RELEVANT_SELECTOR) ||
    element.querySelector(APPLICATION_RELEVANT_SELECTOR) !== null
  );
}

export function shouldRescanFromMutations(
  records: readonly MutationRecord[],
): boolean {
  for (const record of records) {
    if (record.type === "childList") return true;
    if (record.type !== "attributes") continue;

    const attribute = record.attributeName ?? "";
    if (attribute !== "class" && attribute !== "style") return true;
    if (record.target instanceof Element && elementTouchesApplication(record.target)) {
      return true;
    }
  }
  return false;
}
