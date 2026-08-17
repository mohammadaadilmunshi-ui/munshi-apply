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
    '  const page = scanDocument("https://careers.example.com/apply", "Apply");',
    "  const page = scanDocument();",
)
replace_once(
    "apps/extension/src/content/teach-strengthened.test.ts",
    "  cancelTeachInteraction();",
    '  cancelTeachInteraction("cleanup-session");',
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

path = "packages/application-model/src/retrieval.ts"
content = read(path)
content = content.replace(
    'import type { EvidenceGraph, EvidenceNode, TrustLevel } from "./evidence";',
    'import type { SemanticType, TrustLevel } from "@munshi-apply/contracts";\nimport type { EvidenceGraph, EvidenceNode } from "./evidence";',
    1,
)
content = content.replace("  semanticType?: string;", "  semanticType?: SemanticType;", 1)
write(path, content)
