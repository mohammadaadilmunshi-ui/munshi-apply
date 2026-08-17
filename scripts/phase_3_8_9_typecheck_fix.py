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
    "apps/extension/src/content/teach.test.ts",
    '''    const started = beginTeachInteraction("teach-1", control.controlId);
    input.dispatchEvent(new Event("input", { bubbles: true }));''',
    '''    const started = beginTeachInteraction("teach-1", control.controlId);
    input.value = "United States";
    input.dispatchEvent(new Event("input", { bubbles: true }));''',
)

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
