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

function elementTouchesApplication(element: Element): boolean {
  return (
    elementIsApplicationRelevant(element) ||
    element.closest(APPLICATION_RELEVANT_SELECTOR) !== null ||
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

    if (elementTouchesApplication(record.target)) return true;
  }
  return false;
}
