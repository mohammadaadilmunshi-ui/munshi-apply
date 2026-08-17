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
    root.querySelectorAll("h1, h2, h3, h4, h5, h6, [role=heading], legend"),
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
      root.querySelectorAll("h1, h2, h3, h4, h5, h6, [role=heading], legend"),
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
  const ancestry = stableAncestry(element);
  return [
    element.tagName.toLowerCase(),
    element.getAttribute("type") ?? "",
    element.getAttribute("name") ?? "",
    labelFor(element),
'''
new_signature = '''function stableControlSignature(element: Element, label: string): string {
  const ancestry = stableAncestry(element);
  return [
    element.tagName.toLowerCase(),
    element.getAttribute("type") ?? "",
    element.getAttribute("name") ?? "",
    label,
'''
replace_once(old_signature, new_signature, "stable control signature")

old_create = '''  const validation = validationFor(element);
  const controlId = hash(`ctl:${stableControlSignature(element)}`);
  const kind = kindFor(element);
'''
new_create = '''  const validation = validationFor(element);
  const label = labelFor(element);
  const controlId = hash(`ctl:${stableControlSignature(element, label)}`);
  const kind = kindFor(element);
'''
replace_once(old_create, new_create, "createControl identity block")
replace_once('    label: labelFor(element),\n', '    label,\n', "createControl label assignment")

old_scan = '''export function scanDocument(): ApplicationPage {
  const context = scanControlEntries();
'''
new_scan = '''export function scanDocument(): ApplicationPage {
  sectionHeadingCache = new WeakMap<Document | ShadowRoot, Element[]>();
  const context = scanControlEntries();
'''
replace_once(old_scan, new_scan, "scanDocument entry point")

path.write_text(source, encoding="utf-8")
