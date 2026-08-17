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


path = "apps/extension/src/content/teach.ts"
content = read(path)
content = content.replace(
    'target.closest(`[aria-controls=\\"${element.id}\\"]`)',
    'element.id ? target.closest(`[aria-controls="${CSS.escape(element.id)}"]`) : null',
)
write(path, content)

path = "apps/native-host/src/munshi_apply_native/ai_governance.py"
content = read(path)
content = content.replace(
    '            "pricing": self._pricing_status(config.model, now=now),',
    '            "pricing": (\n                self._pricing_status(config.openai_model_for_lane("CHEAP"), now=now)\n                if config.provider != "ollama"\n                else None\n            ),',
    1,
)
write(path, content)

path = "apps/extension/src/messaging/native.ts"
content = read(path)
content = content.replace(
    '''export type AISettings = {
  provider: "openai";
  enabled: boolean;
  model: string;
  monthlyBudgetUsd: number;''',
    '''export type AIProviderChoice = "openai" | "ollama" | "auto";

export type AISettings = {
  provider: AIProviderChoice;
  enabled: boolean;
  model: string;
  cheapModel: string;
  strongModel: string;
  ollamaModel: string;
  preferLocalFallback: boolean;
  monthlyBudgetUsd: number;''',
    1,
)
content = content.replace('  provider: "openai";\n  model: string;\n  responseId: string;', '  provider: "openai" | "ollama";\n  model: string;\n  responseId: string;', 1)
content = content.replace(
    '''export type AIDraftPreview = {
  state: "READY_FOR_PROVIDER";
  providerCallMade: false;
  model: string;
  evidenceIds: string[];''',
    '''export type AIDraftPreview = {
  state: "READY_FOR_PROVIDER";
  providerCallMade: false;
  provider: "openai" | "ollama";
  model: string;
  modelLane: "CHEAP" | "STRONG";
  routeReason: string;
  responseIntent: string;
  styleSamples: number;
  evidenceIds: string[];
  evidenceStats?: Record<string, unknown>;''',
    1,
)
content = content.replace(
    '''export type AIDraftResult = {
  status: "DRAFT_REVIEW_REQUIRED";
  draftId: string;
  draft: AIDraftRecord;
  provider: "openai";
  model: string;''',
    '''export type AIDraftResult = {
  status: "DRAFT_REVIEW_REQUIRED";
  draftId: string;
  draft: AIDraftRecord;
  provider: "openai" | "ollama";
  model: string;
  modelLane: "CHEAP" | "STRONG";
  routeReason: string;
  responseIntent: string;
  styleSamples: number;''',
    1,
)
content = content.replace(
    '''  if (candidate.provider !== "openai") {
    throw new Error("AI settings provider is invalid");
  }
  const keySource = candidate.keySource;''',
    '''  const provider = candidate.provider;
  if (provider !== "openai" && provider !== "ollama" && provider !== "auto") {
    throw new Error("AI settings provider is invalid");
  }
  const keySource = candidate.keySource;''',
    1,
)
content = content.replace(
    '''    "allowResumeEvidence",
    "keyConfigured",''',
    '''    "allowResumeEvidence",
    "preferLocalFallback",
    "keyConfigured",''',
    1,
)
content = content.replace(
    '''  return {
    provider: "openai",
    enabled: candidate.enabled as boolean,
    model: typeof candidate.model === "string" ? candidate.model : "",
    monthlyBudgetUsd,''',
    '''  return {
    provider,
    enabled: candidate.enabled as boolean,
    model: typeof candidate.model === "string" ? candidate.model : "",
    cheapModel: typeof candidate.cheapModel === "string" ? candidate.cheapModel : "",
    strongModel: typeof candidate.strongModel === "string" ? candidate.strongModel : "",
    ollamaModel: typeof candidate.ollamaModel === "string" ? candidate.ollamaModel : "",
    preferLocalFallback: candidate.preferLocalFallback as boolean,
    monthlyBudgetUsd,''',
    1,
)
content = content.replace(
    '''  if (candidate.provider !== "openai") {
    throw new Error("AI draft provider is invalid");
  }''',
    '''  if (candidate.provider !== "openai" && candidate.provider !== "ollama") {
    throw new Error("AI draft provider is invalid");
  }''',
    1,
)
content = content.replace('    provider: "openai",\n    model: stringValue(candidate.model, "AI model"),', '    provider: candidate.provider as "openai" | "ollama",\n    model: stringValue(candidate.model, "AI model"),', 1)
content = content.replace(
    '''        provider: settings.provider,
        enabled: settings.enabled,
        model: settings.model,
        monthlyBudgetUsd: settings.monthlyBudgetUsd,''',
    '''        provider: settings.provider,
        enabled: settings.enabled,
        model: settings.model,
        cheapModel: settings.cheapModel,
        strongModel: settings.strongModel,
        ollamaModel: settings.ollamaModel,
        preferLocalFallback: settings.preferLocalFallback,
        monthlyBudgetUsd: settings.monthlyBudgetUsd,''',
    1,
)
insert_after = '''export async function listOpenAIModels(): Promise<string[]> {
  const result = await sendNative<{ models: string[] }>(
    { type: "LIST_OPENAI_MODELS" },
    15_000,
  );
  return result.models;
}
'''
addition = insert_after + '''
export async function testOllamaConnection(): Promise<{ modelCount: number }> {
  return sendNative<{ modelCount: number }>(
    { type: "TEST_OLLAMA_CONNECTION" },
    15_000,
  );
}

export async function listOllamaModels(): Promise<string[]> {
  const result = await sendNative<{ models: string[] }>(
    { type: "LIST_OLLAMA_MODELS" },
    15_000,
  );
  return result.models;
}

export type WritingStyleStatus = {
  samples: number;
  averageWords: number;
  averageSentenceWords: number;
  contractionRate: number;
  firstPersonRate: number;
  enthusiasmRate: number;
  concisePreference: number;
  instructions: string;
};

export async function getWritingStyle(): Promise<WritingStyleStatus> {
  const raw = await sendNative<Record<string, unknown>>({ type: "GET_WRITING_STYLE" });
  return {
    samples: integerValue(raw.samples, "writing style samples"),
    averageWords: finiteNumber(raw.average_words ?? raw.averageWords, "writing style averageWords"),
    averageSentenceWords: finiteNumber(raw.average_sentence_words ?? raw.averageSentenceWords, "writing style averageSentenceWords"),
    contractionRate: finiteNumber(raw.contraction_rate ?? raw.contractionRate, "writing style contractionRate"),
    firstPersonRate: finiteNumber(raw.first_person_rate ?? raw.firstPersonRate, "writing style firstPersonRate"),
    enthusiasmRate: finiteNumber(raw.enthusiasm_rate ?? raw.enthusiasmRate, "writing style enthusiasmRate"),
    concisePreference: finiteNumber(raw.concise_preference ?? raw.concisePreference, "writing style concisePreference"),
    instructions: stringValue(raw.instructions, "writing style instructions"),
  };
}

export type ResumeEvidenceIngestionResult = {
  sessionId: string;
  resumeId: string;
  sha256: string;
  parser: string;
  evidenceCount: number;
  characterCount: number;
  warnings: string[];
};

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const block = 0x8000;
  for (let index = 0; index < bytes.length; index += block) {
    binary += String.fromCharCode(...bytes.subarray(index, index + block));
  }
  return btoa(binary);
}

export async function ingestResumeEvidence(input: {
  file: File;
  resumeId: string;
  sha256: string;
  applicationId?: string | null;
}): Promise<ResumeEvidenceIngestionResult> {
  const resumeId = input.resumeId.trim();
  const sha256 = input.sha256.toLowerCase().trim();
  if (!resumeId) throw new Error("Résumé evidence indexing requires resumeId");
  if (!/^[a-f0-9]{64}$/.test(sha256)) throw new Error("Résumé evidence indexing requires SHA-256");
  if (input.file.size < 1 || input.file.size > 12 * 1024 * 1024) {
    throw new Error("Résumé evidence indexing accepts files up to 12 MB");
  }
  const sessionId = `resume-${crypto.randomUUID()}`;
  await sendNative(
    {
      type: "BEGIN_DOCUMENT_INGESTION",
      payload: {
        sessionId,
        resumeId,
        filename: input.file.name,
        sha256,
        sizeBytes: input.file.size,
        applicationId: input.applicationId?.trim() || null,
      },
    },
    15_000,
  );
  try {
    const bytes = new Uint8Array(await input.file.arrayBuffer());
    const chunkSize = 384 * 1024;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      const chunk = bytes.subarray(offset, Math.min(bytes.length, offset + chunkSize));
      await sendNative(
        {
          type: "APPEND_DOCUMENT_CHUNK",
          payload: { sessionId, offset, base64: bytesToBase64(chunk) },
        },
        20_000,
      );
    }
    return await sendNative<ResumeEvidenceIngestionResult>(
      { type: "FINISH_DOCUMENT_INGESTION", payload: { sessionId } },
      60_000,
    );
  } catch (error) {
    await sendNative({ type: "CANCEL_DOCUMENT_INGESTION", payload: { sessionId } }).catch(
      () => undefined,
    );
    throw error;
  }
}
'''
if content.count(insert_after) != 1:
    raise RuntimeError("native.ts: OpenAI models insertion point missing")
content = content.replace(insert_after, addition, 1)
write(path, content)

path = "apps/extension/src/sidepanel/ResumeVaultPanel.tsx"
content = read(path)
content = content.replace(
    'import { useMemo, useState, type DragEvent } from "react";\n',
    'import { useMemo, useState, type DragEvent } from "react";\nimport { ingestResumeEvidence } from "../messaging/native";\n',
    1,
)
content = content.replace(
    '''  currentRole,
  onSelected,''',
    '''  currentRole,
  nativeAvailable,
  applicationId,
  onSelected,''',
    1,
)
content = content.replace(
    '''  currentRole: string | null;
  onSelected: (resumeId: string) => void;''',
    '''  currentRole: string | null;
  nativeAvailable: boolean;
  applicationId: string | null;
  onSelected: (resumeId: string) => void;''',
    1,
)
content = content.replace(
    '''      onSelected(resume.resumeId);
      if (source === "TAILORED") setRoleFamily("");
      onNotice(
        `${resume.name} encrypted as ${source === "MASTER" ? "your master résumé" : `a tailored résumé for ${role ?? "this job"}`}.`,
      );
      await onRefresh();''',
    '''      onSelected(resume.resumeId);
      if (source === "TAILORED") setRoleFamily("");
      let evidenceNotice = "";
      if (nativeAvailable) {
        try {
          const indexed = await ingestResumeEvidence({
            file,
            resumeId: resume.resumeId,
            sha256: resume.sha256,
            applicationId: applicationId || null,
          });
          evidenceNotice = ` ${indexed.evidenceCount} résumé evidence chunks indexed for grounded answers.`;
          if (indexed.warnings.length > 0) evidenceNotice += ` ${indexed.warnings.join(" ")}`;
        } catch (error) {
          evidenceNotice = ` The encrypted résumé was saved, but evidence indexing was deferred: ${error instanceof Error ? error.message : "parser unavailable"}.`;
        }
      } else {
        evidenceNotice = " Evidence indexing will run after the native companion is available.";
      }
      onNotice(
        `${resume.name} encrypted as ${source === "MASTER" ? "your master résumé" : `a tailored résumé for ${role ?? "this job"}`}.${evidenceNotice}`,
      );
      await onRefresh();''',
    1,
)
write(path, content)

replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''              currentRole={page?.title ?? null}
              onSelected={setSelectedResumeId}''',
    '''              currentRole={page?.title ?? null}
              nativeAvailable={native.status === "healthy"}
              applicationId={activeApplicationId || null}
              onSelected={setSelectedResumeId}''',
)

write(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    r'''import { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteOpenAIKey,
  getAIControlStatus,
  getWritingStyle,
  listOllamaModels,
  listOpenAIModels,
  saveAISettings,
  setOpenAIKey,
  testOllamaConnection,
  testOpenAIConnection,
  type AIControlStatus,
  type AISettings,
  type WritingStyleStatus,
} from "../messaging/native";

const defaultSettings: AISettings = {
  provider: "auto",
  enabled: false,
  model: "",
  cheapModel: "",
  strongModel: "",
  ollamaModel: "",
  preferLocalFallback: true,
  monthlyBudgetUsd: 0,
  warningBudgetUsd: 0,
  hardStop: true,
  allowApplicationDrafts: false,
  allowProfileEvidence: true,
  allowResumeEvidence: true,
  keyConfigured: false,
  keySource: "none",
};

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 0.01 ? 4 : 2,
    maximumFractionDigits: value < 0.01 ? 6 : 2,
  }).format(value);
}

export function AIControlCenter({ nativeAvailable, nativeIssue }: { nativeAvailable: boolean; nativeIssue?: string }) {
  const [status, setStatus] = useState<AIControlStatus | null>(null);
  const [settings, setSettings] = useState<AISettings>(defaultSettings);
  const [openAIModels, setOpenAIModels] = useState<string[]>([]);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [style, setStyle] = useState<WritingStyleStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);

  const refresh = useCallback(async () => {
    if (!nativeAvailable) return;
    const [next, nextStyle] = await Promise.all([getAIControlStatus(), getWritingStyle()]);
    setStatus(next);
    setSettings(next.settings);
    setStyle(nextStyle);
    setMessageIsError(false);
  }, [nativeAvailable]);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Unable to load AI controls");
    });
  }, [refresh]);

  const budgetPercent = useMemo(() => {
    if (!status || settings.monthlyBudgetUsd <= 0) return 0;
    return Math.min(100, (status.usage.projectedUsd / settings.monthlyBudgetUsd) * 100);
  }, [settings.monthlyBudgetUsd, status]);

  async function run(task: () => Promise<void>): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await task();
      setMessageIsError(false);
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "AI control action failed");
    } finally {
      setBusy(false);
    }
  }

  async function storeKey(): Promise<void> {
    if (!apiKey.trim()) return;
    await run(async () => {
      await setOpenAIKey(apiKey.trim());
      setApiKey("");
      await refresh();
      setMessage("OpenAI credential stored in macOS Keychain. MUNSHI never displays the saved secret.");
    });
  }

  async function removeKey(): Promise<void> {
    await run(async () => {
      await deleteOpenAIKey();
      setOpenAIModels([]);
      await refresh();
      setMessage("Stored OpenAI credential removed from macOS Keychain.");
    });
  }

  async function testOpenAI(): Promise<void> {
    await run(async () => {
      const connection = await testOpenAIConnection();
      const models = await listOpenAIModels();
      setOpenAIModels(models);
      setMessage(`OpenAI verified. ${connection.modelCount} models visible; no generation request was made.`);
    });
  }

  async function testOllama(): Promise<void> {
    await run(async () => {
      const connection = await testOllamaConnection();
      const models = await listOllamaModels();
      setOllamaModels(models);
      setMessage(`Local Ollama verified. ${connection.modelCount} local models visible; no paid provider is involved.`);
    });
  }

  async function saveControls(): Promise<void> {
    await run(async () => {
      const saved = await saveAISettings(settings);
      setSettings(saved);
      await refresh();
      setMessage("Provider routing, evidence permissions, and budget controls saved locally.");
    });
  }

  if (!nativeAvailable) {
    return (
      <section>
        <p className="eyebrow">Owner-controlled intelligence</p>
        <h2>AI Control Center</h2>
        <div className="safety-callout">
          <strong>{nativeIssue ? "Native companion update required" : "Native companion required"}</strong>
          <span>{nativeIssue ?? "Provider credentials, local models, evidence indexing, and budget enforcement live in the native companion."}</span>
        </div>
      </section>
    );
  }

  return (
    <section>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Owner-controlled intelligence</p>
          <h2>AI Control Center</h2>
        </div>
        <span className="badge">{settings.provider.toUpperCase()}</span>
      </div>

      <p>Choose automatic routing, OpenAI, or local Ollama. MUNSHI retrieves only relevant evidence, routes routine questions cheaply, escalates harder narrative questions, and always returns a reviewable draft.</p>

      <h3>Provider routing</h3>
      <div className="form-grid">
        <label>
          <span>Provider policy</span>
          <select value={settings.provider} onChange={(event) => setSettings((current) => ({ ...current, provider: event.target.value as AISettings["provider"] }))}>
            <option value="auto">Auto · prefer available local fallback</option>
            <option value="openai">OpenAI</option>
            <option value="ollama">Local Ollama</option>
          </select>
        </label>
        <label className="answer-approval">
          <input type="checkbox" checked={settings.preferLocalFallback} onChange={(event) => setSettings((current) => ({ ...current, preferLocalFallback: event.target.checked }))} />
          Use local Ollama as fallback when configured
        </label>
        <label>
          <span>Cheap / routine OpenAI model</span>
          <input type="text" list="munshi-openai-models" value={settings.cheapModel} placeholder="e.g. configured low-cost model" onChange={(event) => setSettings((current) => ({ ...current, cheapModel: event.target.value, model: current.model || event.target.value }))} />
        </label>
        <label>
          <span>Strong reasoning OpenAI model</span>
          <input type="text" list="munshi-openai-models" value={settings.strongModel} placeholder="e.g. configured strong model" onChange={(event) => setSettings((current) => ({ ...current, strongModel: event.target.value }))} />
        </label>
        <datalist id="munshi-openai-models">{openAIModels.map((model) => <option key={model} value={model} />)}</datalist>
        <label>
          <span>Local Ollama model</span>
          <input type="text" list="munshi-ollama-models" value={settings.ollamaModel} placeholder="e.g. qwen / llama model installed locally" onChange={(event) => setSettings((current) => ({ ...current, ollamaModel: event.target.value }))} />
        </label>
        <datalist id="munshi-ollama-models">{ollamaModels.map((model) => <option key={model} value={model} />)}</datalist>
      </div>
      <div className="record-actions">
        <button className="quiet" type="button" disabled={busy} onClick={() => void testOllama()}>Test local Ollama & load models</button>
        <button className="quiet" type="button" disabled={busy || !settings.keyConfigured} onClick={() => void testOpenAI()}>Test OpenAI & load models</button>
      </div>

      <h3>OpenAI credential</h3>
      <div className="cloud-pairing">
        <p>Saved credential: {settings.keyConfigured ? `•••••••• · ${settings.keySource}` : "none"}</p>
        <label>
          <span>{settings.keyConfigured ? "Replace API key" : "OpenAI API key"}</span>
          <input type="password" autoComplete="off" spellCheck={false} value={apiKey} placeholder="Paste key on your Mac" onChange={(event) => setApiKey(event.target.value)} />
        </label>
        <div className="record-actions">
          <button className="primary" type="button" disabled={busy || !apiKey.trim()} onClick={() => void storeKey()}>{settings.keyConfigured ? "Replace Keychain key" : "Store in macOS Keychain"}</button>
          <button className="quiet destructive" type="button" disabled={busy || !settings.keyConfigured} onClick={() => void removeKey()}>Delete stored key</button>
        </div>
      </div>

      <h3>Draft permissions</h3>
      <div className="form-grid">
        <label className="answer-approval"><input type="checkbox" checked={settings.enabled} onChange={(event) => setSettings((current) => ({ ...current, enabled: event.target.checked }))} />AI master switch</label>
        <label className="answer-approval"><input type="checkbox" checked={settings.allowApplicationDrafts} onChange={(event) => setSettings((current) => ({ ...current, allowApplicationDrafts: event.target.checked }))} />Allow evidence-grounded application drafts</label>
        <label className="answer-approval"><input type="checkbox" checked={settings.allowProfileEvidence} onChange={(event) => setSettings((current) => ({ ...current, allowProfileEvidence: event.target.checked }))} />Use verified profile evidence</label>
        <label className="answer-approval"><input type="checkbox" checked={settings.allowResumeEvidence} onChange={(event) => setSettings((current) => ({ ...current, allowResumeEvidence: event.target.checked }))} />Use indexed résumé evidence</label>
      </div>

      <h3>Paid-provider budget</h3>
      <div className="form-grid">
        <label><span>Monthly maximum (USD)</span><input type="number" min="0" step="0.01" value={settings.monthlyBudgetUsd} onChange={(event) => setSettings((current) => ({ ...current, monthlyBudgetUsd: Number(event.target.value) }))} /><small>$0 blocks paid-provider generation; local Ollama can still be used when configured.</small></label>
        <label><span>Warning threshold (USD)</span><input type="number" min="0" step="0.01" value={settings.warningBudgetUsd} onChange={(event) => setSettings((current) => ({ ...current, warningBudgetUsd: Number(event.target.value) }))} /></label>
        <label className="answer-approval"><input type="checkbox" checked={settings.hardStop} onChange={(event) => setSettings((current) => ({ ...current, hardStop: event.target.checked }))} />Hard stop paid generation when projected spend exceeds maximum</label>
      </div>

      {status && (
        <>
          <div className="metrics">
            <article><strong>{money(status.usage.spentUsd)}</strong><span>paid spend</span></article>
            <article><strong>{money(status.usage.reservedUsd)}</strong><span>reserved</span></article>
            <article><strong>{status.usage.requestCount}</strong><span>provider runs</span></article>
          </div>
          <label><span>Paid usage · {money(status.usage.projectedUsd)} projected · {money(status.usage.remainingUsd)} remaining</span><progress max={100} value={budgetPercent} /></label>
        </>
      )}

      <h3>Writing preference learning</h3>
      <div className="cloud-connection">
        <strong>{style?.samples ?? 0} approved owner edits learned</strong>
        <span>{style?.instructions ?? "MUNSHI will learn style only from generated drafts that you edit and explicitly approve."}</span>
      </div>

      <h3>Pricing gate</h3>
      {status?.pricing ? (
        <div className="cloud-connection">
          <strong>{status.pricing.model}</strong>
          <span>{money(status.pricing.inputUsdPerMillionTokens)} input / 1M · {money(status.pricing.outputUsdPerMillionTokens)} output / 1M</span>
          {status.pricing.stale && <span className="diagnostic-error">Pricing is stale; paid generation remains blocked until re-verified.</span>}
        </div>
      ) : settings.provider === "ollama" ? (
        <div className="cloud-connection"><strong>Local provider selected</strong><span>Ollama runs on loopback and does not use the paid-provider budget.</span></div>
      ) : (
        <div className="safety-callout"><strong>No verified pricing for the current OpenAI routine model</strong><span>Paid generation will not run without a known current pricing snapshot. Local fallback can remain available.</span></div>
      )}

      <div className="record-actions">
        <button className="primary" type="button" disabled={busy} onClick={() => void saveControls()}>Save AI controls</button>
        <button className="quiet" type="button" disabled={busy} onClick={() => void refresh()}>Refresh status</button>
      </div>
      {message && <div className={messageIsError ? "diagnostic-error" : "notice"}>{message}</div>}

      <div className="safety-callout">
        <strong>Truth boundary, not a usability barrier</strong>
        <span>Generated answers can cover job-specific narrative questions using job context plus verified candidate evidence. Work authorization, sponsorship, EEO/demographics, factual disclosures, security checkpoints, and final submission are not invented by AI. Every generated answer remains reviewable and must be approved before guarded fill.</span>
      </div>
    </section>
  );
}
''',
)

path = "apps/extension/src/sidepanel/AIDraftReview.tsx"
content = read(path)
content = content.replace(
    '''          <strong>{preview.model}</strong>
          <span>{preview.evidenceIds.length} authoritative evidence items</span>''',
    '''          <strong>{preview.provider} · {preview.model} · {preview.modelLane.toLowerCase()} lane</strong>
          <span>{preview.responseIntent.replaceAll("_", " ")} · {preview.evidenceIds.length} authoritative evidence items</span>
          <span>{preview.routeReason}</span>
          <span>Writing-style samples: {preview.styleSamples}</span>''',
    1,
)
content = content.replace(
    '''            <span>Model: {draft.model}</span>''',
    '''            <span>Provider / model: {draft.provider} · {draft.model}</span>''',
    1,
)
write(path, content)

write(
    "apps/native-host/tests/test_document_ingestion.py",
    r'''from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.document_ingestion import DocumentIngestionService


def make_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>',
        )
    return buffer.getvalue()


def test_chunked_resume_ingestion_verifies_hash_and_builds_evidence(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "runtime.sqlite", migrations)
    database.migrate()
    service = DocumentIngestionService(database)
    data = make_docx(
        "Recruiting operations experience improved onboarding and candidate coordination with Excel analytics."
    )
    digest = hashlib.sha256(data).hexdigest()
    started = service.begin(
        {
            "sessionId": "resume-session-0001",
            "resumeId": "resume-1",
            "filename": "resume.docx",
            "sha256": digest,
            "sizeBytes": len(data),
            "applicationId": None,
        }
    )
    assert started["receivedBytes"] == 0
    service.append(
        {
            "sessionId": "resume-session-0001",
            "offset": 0,
            "base64": base64.b64encode(data).decode("ascii"),
        }
    )
    finished = service.finish({"sessionId": "resume-session-0001"})
    assert finished["sha256"] == digest
    assert finished["evidenceCount"] >= 1
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT kind, trust_level, source FROM evidence_nodes WHERE source LIKE 'resume:resume-1:%'"
        ).fetchall()
    assert rows
    assert rows[0]["kind"] == "RESUME_BULLET"
    assert rows[0]["trust_level"] == "DOCUMENT_CONFIRMED"
''',
)

write(
    "apps/native-host/tests/test_intelligence_router.py",
    r'''from __future__ import annotations

from munshi_apply_native.ai_settings import AIConfiguration
from munshi_apply_native.intelligence_router import choose_intelligence_route
from munshi_apply_native.response_planner import plan_job_response


class FakeStore:
    def __init__(self, source: str) -> None:
        self.source = source

    def key_source(self) -> str:
        return self.source


def test_auto_route_can_prefer_local_and_retain_openai_fallback() -> None:
    config = AIConfiguration(
        provider="auto",
        enabled=True,
        model="cheap",
        cheap_model="cheap",
        strong_model="strong",
        ollama_model="qwen-local",
        prefer_local_fallback=True,
    )
    route = choose_intelligence_route(
        config,
        FakeStore("keychain"),  # type: ignore[arg-type]
        plan_job_response("Why this role?", "WHY_ROLE"),
    )
    assert route.provider == "ollama"
    assert route.fallback_provider == "openai"


def test_strong_lane_selects_strong_openai_model() -> None:
    config = AIConfiguration(
        provider="openai",
        enabled=True,
        model="cheap",
        cheap_model="cheap",
        strong_model="strong",
        prefer_local_fallback=False,
    )
    route = choose_intelligence_route(
        config,
        FakeStore("keychain"),  # type: ignore[arg-type]
        plan_job_response("Tell us about a time you solved a conflict", "BEHAVIORAL_EXAMPLE"),
    )
    assert route.provider == "openai"
    assert route.model == "strong"
    assert route.lane == "STRONG"
''',
)

write(
    "apps/extension/src/content/teach-strengthened.test.ts",
    r'''import { afterEach, describe, expect, it } from "vitest";
import { beginTeachInteraction, cancelTeachInteraction, finishTeachInteraction } from "./teach";
import { scanDocument } from "./scanner";

function installHtml(): string {
  document.body.innerHTML = `
    <label for="industry">Industry</label>
    <input id="industry" role="combobox" aria-controls="industry-list" />
    <ul id="industry-list" role="listbox"><li role="option">Automotive</li></ul>
    <button id="unrelated">Unrelated</button>
  `;
  const page = scanDocument("https://careers.example.com/apply", "Apply");
  const control = page.controls.find((item) => item.label.includes("Industry"));
  if (!control) throw new Error("fixture control not found");
  return control.controlId;
}

afterEach(() => {
  cancelTeachInteraction();
  document.body.innerHTML = "";
});

describe("strengthened Teach MUNSHI capture", () => {
  it("does not promote unrelated page clicking into a reusable recipe", () => {
    const controlId = installHtml();
    beginTeachInteraction("teach-one-0001", controlId);
    document.querySelector<HTMLButtonElement>("#unrelated")!.click();
    const capture = finishTeachInteraction("teach-one-0001");
    expect(capture.changed).toBe(false);
    expect(capture.reusable).toBe(false);
    expect(capture.quality.score).toBeLessThan(0.8);
  });

  it("captures committed before and after state for the selected control", () => {
    const controlId = installHtml();
    beginTeachInteraction("teach-two-0002", controlId);
    const input = document.querySelector<HTMLInputElement>("#industry")!;
    input.value = "Automotive";
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const capture = finishTeachInteraction("teach-two-0002");
    expect(capture.changed).toBe(true);
    expect(capture.quality.valueCommitted).toBe(true);
    expect(capture.beforeState.value).not.toBe(capture.afterState.value);
    expect(capture.quality.score).toBeGreaterThanOrEqual(0.8);
  });
});
''',
)
