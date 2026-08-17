from pathlib import Path

path = Path("apps/extension/src/content/scanner.ts")
source = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global source
    if source.count(old) != 1:
        raise SystemExit(f"Expected exactly one {label}")
    source = source.replace(old, new, 1)


old_store = 'const controlHints = createBoundedHintStore<Control>();\n'
replace_once(
    old_store,
    old_store
    + 'let sectionHeadingCache = new WeakMap<Document | ShadowRoot, Element[]>();\n',
    "bounded control hint declaration",
)

old_section = '''  const root = element.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return "";
  const preceding = Array.from(
    root.querySelectorAll("h1, h2, h3, h4, h5, h6, [role='heading'], legend"),
  )
    .filter(
      (candidate) =>
        candidate !== element &&
        isVisible(candidate) &&
        Boolean(
          candidate.compareDocumentPosition(element) &
            Node.DOCUMENT_POSITION_FOLLOWING,
        ),
    )
    .map((candidate) => ({ candidate, text: headingText(candidate) }))
    .filter((item) => Boolean(item.text));
'''
new_section = '''  const root = element.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return "";
  let headings = sectionHeadingCache.get(root);
  if (!headings) {
    headings = Array.from(
      root.querySelectorAll("h1, h2, h3, h4, h5, h6, [role='heading'], legend"),
    ).filter(isVisible);
    sectionHeadingCache.set(root, headings);
  }
  const preceding = headings
    .filter(
      (candidate) =>
        candidate !== element &&
        Boolean(
          candidate.compareDocumentPosition(element) &
            Node.DOCUMENT_POSITION_FOLLOWING,
        ),
    )
    .map((candidate) => ({ candidate, text: headingText(candidate) }))
    .filter((item) => Boolean(item.text));
'''
replace_once(old_section, new_section, "section heading query block")

old_signature = '''function stableControlSignature(element: Element): string {
  const url = new URL(window.location.href);
  const type = element instanceof HTMLInputElement ? element.type : "";
  const optionValue =
    element instanceof HTMLInputElement &&
    (element.type === "radio" ||
      element.type === "checkbox" ||
      ["button", "submit", "reset"].includes(element.type))
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
'''
new_signature = '''function stableControlSignature(element: Element, label: string): string {
  const url = new URL(window.location.href);
  const type = element instanceof HTMLInputElement ? element.type : "";
  const optionValue =
    element instanceof HTMLInputElement &&
    (element.type === "radio" ||
      element.type === "checkbox" ||
      ["button", "submit", "reset"].includes(element.type))
      ? element.value
      : "";
  return [
    url.origin,
    url.pathname,
    element.tagName,
    element.id,
    compactText(element.getAttribute("name")),
    type,
    label,
'''
replace_once(old_signature, new_signature, "stable control signature")

old_create = '''  const validation = validationState(element);
  const validationMessage =
    validationMessageFor(element) || validation.validationMessage;
  const repeat = repeatMetadataFor(element);
  const fileFingerprint =
    element instanceof HTMLInputElement && element.type === "file"
      ? fileFingerprintFor(element)
      : null;
  const kind = kindFor(element);
  const options = optionsFor(element);
  return {
    controlId: `ctl-${hash(stableControlSignature(element))}`,
'''
new_create = '''  const validation = validationState(element);
  const validationMessage =
    validationMessageFor(element) || validation.validationMessage;
  const repeat = repeatMetadataFor(element);
  const fileFingerprint =
    element instanceof HTMLInputElement && element.type === "file"
      ? fileFingerprintFor(element)
      : null;
  const kind = kindFor(element);
  const options = optionsFor(element);
  const label = labelFor(element);
  return {
    controlId: `ctl-${hash(stableControlSignature(element, label))}`,
'''
replace_once(old_create, new_create, "createControl identity block")
replace_once('    label: labelFor(element),\n', '    label,\n', "createControl label assignment")

old_scan = '''export function scanDocument(): ApplicationPage {
  const entries = scanControlEntries();
'''
new_scan = '''export function scanDocument(): ApplicationPage {
  sectionHeadingCache = new WeakMap<Document | ShadowRoot, Element[]>();
  const entries = scanControlEntries();
'''
replace_once(old_scan, new_scan, "scanDocument entry point")

path.write_text(source, encoding="utf-8")
