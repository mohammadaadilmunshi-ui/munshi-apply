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

function elementIsApplicationRelevant(element: Element): boolean {
  return element.matches(APPLICATION_RELEVANT_SELECTOR);
}

function elementContainsApplicationControl(element: Element): boolean {
  return element.querySelector(APPLICATION_RELEVANT_SELECTOR) !== null;
}

function nodeAddsOrRemovesApplicationControl(node: Node): boolean {
  return (
    node instanceof Element &&
    (elementIsApplicationRelevant(node) ||
      elementContainsApplicationControl(node))
  );
}

function childListTouchesApplication(record: MutationRecord): boolean {
  return [...record.addedNodes, ...record.removedNodes].some(
    nodeAddsOrRemovesApplicationControl,
  );
}

export function shouldRescanFromMutations(
  records: readonly MutationRecord[],
): boolean {
  for (const record of records) {
    if (record.type === "childList") {
      if (childListTouchesApplication(record)) return true;
      continue;
    }
    if (record.type !== "attributes") continue;
    if (!(record.target instanceof Element)) continue;

    const attribute = record.attributeName ?? "";
    if (attribute === "hidden" || attribute === "aria-hidden") {
      return true;
    }

    if (attribute === "class" || attribute === "style") {
      if (
        elementIsApplicationRelevant(record.target) ||
        elementContainsApplicationControl(record.target)
      ) {
        return true;
      }
      continue;
    }

    return true;
  }
  return false;
}
