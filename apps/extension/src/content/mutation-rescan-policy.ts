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

const SUBTREE_VISIBILITY_ATTRIBUTES = new Set([
  "aria-hidden",
  "class",
  "hidden",
  "style",
]);

function elementIsApplicationRelevant(element: Element): boolean {
  return element.matches(APPLICATION_RELEVANT_SELECTOR);
}

function elementIsInsideApplicationControl(element: Element): boolean {
  return (
    elementIsApplicationRelevant(element) ||
    element.closest(APPLICATION_RELEVANT_SELECTOR) !== null
  );
}

function elementContainsApplicationControl(element: Element): boolean {
  return element.querySelector(APPLICATION_RELEVANT_SELECTOR) !== null;
}

function elementTouchesApplication(element: Element): boolean {
  return (
    elementIsInsideApplicationControl(element) ||
    elementContainsApplicationControl(element)
  );
}

export function isApplicationRelevantTarget(
  target: EventTarget | null,
): boolean {
  return target instanceof Element && elementTouchesApplication(target);
}

function nodeAddsOrRemovesApplicationControl(node: Node): boolean {
  return node instanceof Element && elementTouchesApplication(node);
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

    if (elementIsInsideApplicationControl(record.target)) return true;

    const attribute = record.attributeName ?? "";
    if (
      SUBTREE_VISIBILITY_ATTRIBUTES.has(attribute) &&
      elementContainsApplicationControl(record.target)
    ) {
      return true;
    }
  }
  return false;
}
