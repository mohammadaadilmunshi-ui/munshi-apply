from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:100]!r}")
    write(path, content.replace(old, new, 1))


replace_once(
    "apps/extension/src/content/teach-strengthened.test.ts",
    'import { afterEach, describe, expect, it } from "vitest";',
    '// @vitest-environment jsdom\n\nimport { afterEach, beforeEach, describe, expect, it, vi } from "vitest";',
)
replace_once(
    "apps/extension/src/content/teach-strengthened.test.ts",
    '  const page = scanDocument("https://careers.example.com/apply", "Apply");',
    "  const page = scanDocument();",
)
replace_once(
    "apps/extension/src/content/teach-strengthened.test.ts",
    "afterEach(() => {",
    '''beforeEach(() => {
  window.history.replaceState({}, "", "/apply");
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    bottom: 40,
    height: 30,
    left: 10,
    right: 210,
    top: 10,
    width: 200,
    x: 10,
    y: 10,
    toJSON: () => ({}),
  });
});

afterEach(() => {''',
)
replace_once(
    "apps/extension/src/content/teach-strengthened.test.ts",
    "  cancelTeachInteraction();",
    '  cancelTeachInteraction("cleanup-session");',
)
replace_once(
    "apps/extension/src/content/teach-strengthened.test.ts",
    "    expect(capture.beforeState.value).not.toBe(capture.afterState.value);",
    "    expect(capture.beforeState.valueLength).not.toBe(capture.afterState.valueLength);\n    expect(JSON.stringify(capture)).not.toContain(\"Automotive\");",
)

replace_once(
    "apps/extension/src/content/teach.test.ts",
    '''    const started = beginTeachInteraction("teach-1", control.controlId);
    input.dispatchEvent(new Event("input", { bubbles: true }));''',
    '''    const started = beginTeachInteraction("teach-1", control.controlId);
    input.value = "United States";
    input.dispatchEvent(new Event("input", { bubbles: true }));''',
)

path = "apps/extension/src/content/teach.ts"
content = read(path)
content = content.replace(
    '''function stateFor(element: HTMLElement): Record<string, unknown> {
  const input = element instanceof HTMLInputElement ? element : null;
  const select = element instanceof HTMLSelectElement ? element : null;
  const textarea = element instanceof HTMLTextAreaElement ? element : null;
  return {
    value:
      input?.value ??
      select?.value ??
      textarea?.value ??
      element.textContent ??
      "",
    checked: input?.checked ?? element.getAttribute("aria-checked"),
    selected: element.getAttribute("aria-selected"),
    expanded: element.getAttribute("aria-expanded"),
    invalid: element.getAttribute("aria-invalid"),
    disabled:
      input?.disabled ??
      select?.disabled ??
      textarea?.disabled ??
      element.getAttribute("aria-disabled"),
    role: element.getAttribute("role"),
  };
}

function marker(element: HTMLElement): string {
  const input = element instanceof HTMLInputElement ? element : null;
  const select = element instanceof HTMLSelectElement ? element : null;
  const textarea = element instanceof HTMLTextAreaElement ? element : null;
  void input;
  void select;
  void textarea;
  return JSON.stringify(stateFor(element));
}''',
    '''function controlValue(element: HTMLElement): string {
  if (element instanceof HTMLInputElement) return element.value;
  if (element instanceof HTMLSelectElement) return element.value;
  if (element instanceof HTMLTextAreaElement) return element.value;
  return element.textContent ?? "";
}

function stateFor(element: HTMLElement): Record<string, unknown> {
  const input = element instanceof HTMLInputElement ? element : null;
  const select = element instanceof HTMLSelectElement ? element : null;
  const textarea = element instanceof HTMLTextAreaElement ? element : null;
  const value = controlValue(element);
  return {
    valuePresent: value.length > 0,
    valueLength: value.length,
    checked: input?.checked ?? element.getAttribute("aria-checked"),
    selected: element.getAttribute("aria-selected"),
    expanded: element.getAttribute("aria-expanded"),
    invalid: element.getAttribute("aria-invalid"),
    disabled:
      input?.disabled ??
      select?.disabled ??
      textarea?.disabled ??
      element.getAttribute("aria-disabled"),
    role: element.getAttribute("role"),
  };
}

function marker(element: HTMLElement): string {
  return JSON.stringify({
    ...stateFor(element),
    __privateValue: controlValue(element),
  });
}

function redactedMarkerState(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as Record<string, unknown>;
  delete parsed.__privateValue;
  return parsed;
}

function eventTargetsTeachControl(
  element: HTMLElement,
  target: Element | null,
): boolean {
  if (!target) return false;
  if (target === element || element.contains(target)) return true;
  const popupIds = (element.getAttribute("aria-controls") ?? "")
    .split(/\\s+/)
    .filter(Boolean);
  let cursor: Element | null = target;
  while (cursor) {
    if (cursor.id && popupIds.includes(cursor.id)) return true;
    cursor = cursor.parentElement;
  }
  return false;
}''',
    1,
)
content = content.replace(
    '''        const target = event.target instanceof Element ? event.target : null;
        const related =
          target === element ||
          Boolean(
            target &&
              (element.contains(target) || element.id
                ? target.closest(`[aria-controls="${CSS.escape(element.id)}"]`)
                : null),
          );''',
    '''        const target = event.target instanceof Element ? event.target : null;
        const related = eventTargetsTeachControl(element, target);''',
    1,
)
content = content.replace(
    '''  const beforeState = JSON.parse(
    current.beforeMarker,
  ) as Record<string, unknown>;
  const afterState = JSON.parse(afterMarker) as Record<string, unknown>;''',
    '''  const beforeState = redactedMarkerState(current.beforeMarker);
  const afterState = redactedMarkerState(afterMarker);''',
    1,
)
write(path, content)

replace_once(
    "apps/extension/src/messaging/native-runtime.test.ts",
    '''            ai_draft_lifecycle: true,
          },''',
    '''            ai_draft_lifecycle: true,
            document_evidence_ingestion: true,
            provider_routing: true,
            writing_style_learning: true,
          },''',
)

replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''const defaultAISettings: AISettings = {
  provider: "openai",
  enabled: false,
  model: "",
  monthlyBudgetUsd: 0,''',
    '''const defaultAISettings: AISettings = {
  provider: "auto",
  enabled: false,
  model: "",
  cheapModel: "",
  strongModel: "",
  ollamaModel: "",
  preferLocalFallback: true,
  monthlyBudgetUsd: 0,''',
)

replace_once(
    "apps/extension/src/sidepanel/ResumeVaultPanel.tsx",
    "            sha256: resume.sha256,",
    '            sha256: resume.sha256 ?? "",',
)

path = "apps/extension/src/messaging/native.ts"
content = read(path)
content = content.replace(
    '    "allowResumeEvidence",\n    "preferLocalFallback",\n    "keyConfigured",',
    '    "allowResumeEvidence",\n    "keyConfigured",',
    1,
)
content = content.replace(
    "    preferLocalFallback: candidate.preferLocalFallback as boolean,",
    "    preferLocalFallback: candidate.preferLocalFallback !== false,",
    1,
)
write(path, content)

path = "packages/application-model/src/retrieval.ts"
content = read(path)
content = content.replace(
    'import type { EvidenceGraph, EvidenceNode, TrustLevel } from "./evidence";',
    'import type { SemanticType, TrustLevel } from "@munshi-apply/contracts";\nimport type { EvidenceGraph, EvidenceNode } from "./evidence";',
    1,
)
content = content.replace("  semanticType?: string;", "  semanticType?: SemanticType;", 1)
content = content.replace(
    '''const trustWeight: Record<TrustLevel, number> = {
  VERIFIED: 1,
  USER_CONFIRMED: 0.96,
  DOCUMENT_CONFIRMED: 0.94,
  IMPORTED: 0.62,
  GENERATED: 0.15,
};''',
    '''const trustWeight: Record<TrustLevel, number> = {
  VERIFIED: 1,
  USER_CONFIRMED: 0.96,
  DOCUMENT_CONFIRMED: 0.94,
  DERIVED: 0.7,
  LEARNED: 0.72,
  GENERATED: 0.15,
  UNKNOWN: 0.05,
};''',
    1,
)
write(path, content)
