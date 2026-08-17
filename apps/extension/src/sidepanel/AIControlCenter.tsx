import { useCallback, useEffect, useMemo, useState } from "react";
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

export function AIControlCenter({
  nativeAvailable,
  nativeIssue,
}: {
  nativeAvailable: boolean;
  nativeIssue?: string;
}) {
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
    const [next, nextStyle] = await Promise.all([
      getAIControlStatus(),
      getWritingStyle(),
    ]);
    setStatus(next);
    setSettings(next.settings);
    setStyle(nextStyle);
    setMessageIsError(false);
  }, [nativeAvailable]);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessageIsError(true);
      setMessage(
        error instanceof Error ? error.message : "Unable to load AI controls",
      );
    });
  }, [refresh]);

  const budgetPercent = useMemo(() => {
    if (!status || settings.monthlyBudgetUsd <= 0) return 0;
    return Math.min(
      100,
      (status.usage.projectedUsd / settings.monthlyBudgetUsd) * 100,
    );
  }, [settings.monthlyBudgetUsd, status]);

  async function run(task: () => Promise<void>): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await task();
      setMessageIsError(false);
    } catch (error) {
      setMessageIsError(true);
      setMessage(
        error instanceof Error ? error.message : "AI control action failed",
      );
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
      setMessage(
        "OpenAI credential stored in macOS Keychain. MUNSHI never displays the saved secret.",
      );
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
      setMessage(
        `OpenAI verified. ${connection.modelCount} models visible; no generation request was made.`,
      );
    });
  }

  async function testOllama(): Promise<void> {
    await run(async () => {
      const connection = await testOllamaConnection();
      const models = await listOllamaModels();
      setOllamaModels(models);
      setMessage(
        `Local Ollama verified. ${connection.modelCount} local models visible; no paid provider is involved.`,
      );
    });
  }

  async function saveControls(): Promise<void> {
    await run(async () => {
      const saved = await saveAISettings(settings);
      setSettings(saved);
      await refresh();
      setMessage(
        "Provider routing, evidence permissions, and budget controls saved locally.",
      );
    });
  }

  if (!nativeAvailable) {
    return (
      <section>
        <p className="eyebrow">Owner-controlled intelligence</p>
        <h2>AI Control Center</h2>
        <div className="safety-callout">
          <strong>
            {nativeIssue
              ? "Native companion update required"
              : "Native companion required"}
          </strong>
          <span>
            {nativeIssue ??
              "Provider credentials, local models, evidence indexing, and budget enforcement live in the native companion."}
          </span>
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

      <p>
        Choose automatic routing, OpenAI, or local Ollama. MUNSHI retrieves only
        relevant evidence, routes routine questions cheaply, escalates harder
        narrative questions, and always returns a reviewable draft.
      </p>

      <h3>Provider routing</h3>
      <div className="form-grid">
        <label>
          <span>Provider policy</span>
          <select
            value={settings.provider}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                provider: event.target.value as AISettings["provider"],
              }))
            }
          >
            <option value="auto">Auto · prefer available local fallback</option>
            <option value="openai">OpenAI</option>
            <option value="ollama">Local Ollama</option>
          </select>
        </label>
        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.preferLocalFallback}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                preferLocalFallback: event.target.checked,
              }))
            }
          />
          Use local Ollama as fallback when configured
        </label>
        <label>
          <span>Cheap / routine OpenAI model</span>
          <input
            type="text"
            list="munshi-openai-models"
            value={settings.cheapModel}
            placeholder="e.g. configured low-cost model"
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                cheapModel: event.target.value,
                model: current.model || event.target.value,
              }))
            }
          />
        </label>
        <label>
          <span>Strong reasoning OpenAI model</span>
          <input
            type="text"
            list="munshi-openai-models"
            value={settings.strongModel}
            placeholder="e.g. configured strong model"
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                strongModel: event.target.value,
              }))
            }
          />
        </label>
        <datalist id="munshi-openai-models">
          {openAIModels.map((model) => (
            <option key={model} value={model} />
          ))}
        </datalist>
        <label>
          <span>Local Ollama model</span>
          <input
            type="text"
            list="munshi-ollama-models"
            value={settings.ollamaModel}
            placeholder="e.g. qwen / llama model installed locally"
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                ollamaModel: event.target.value,
              }))
            }
          />
        </label>
        <datalist id="munshi-ollama-models">
          {ollamaModels.map((model) => (
            <option key={model} value={model} />
          ))}
        </datalist>
      </div>
      <div className="record-actions">
        <button
          className="quiet"
          type="button"
          disabled={busy}
          onClick={() => void testOllama()}
        >
          Test local Ollama & load models
        </button>
        <button
          className="quiet"
          type="button"
          disabled={busy || !settings.keyConfigured}
          onClick={() => void testOpenAI()}
        >
          Test OpenAI & load models
        </button>
      </div>

      <h3>OpenAI credential</h3>
      <div className="cloud-pairing">
        <p>
          Saved credential:{" "}
          {settings.keyConfigured ? `•••••••• · ${settings.keySource}` : "none"}
        </p>
        <label>
          <span>
            {settings.keyConfigured ? "Replace API key" : "OpenAI API key"}
          </span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={apiKey}
            placeholder="Paste key on your Mac"
            onChange={(event) => setApiKey(event.target.value)}
          />
        </label>
        <div className="record-actions">
          <button
            className="primary"
            type="button"
            disabled={busy || !apiKey.trim()}
            onClick={() => void storeKey()}
          >
            {settings.keyConfigured
              ? "Replace Keychain key"
              : "Store in macOS Keychain"}
          </button>
          <button
            className="quiet destructive"
            type="button"
            disabled={busy || !settings.keyConfigured}
            onClick={() => void removeKey()}
          >
            Delete stored key
          </button>
        </div>
      </div>

      <h3>Draft permissions</h3>
      <div className="form-grid">
        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.enabled}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                enabled: event.target.checked,
              }))
            }
          />
          AI master switch
        </label>
        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.allowApplicationDrafts}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                allowApplicationDrafts: event.target.checked,
              }))
            }
          />
          Allow evidence-grounded application drafts
        </label>
        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.allowProfileEvidence}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                allowProfileEvidence: event.target.checked,
              }))
            }
          />
          Use verified profile evidence
        </label>
        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.allowResumeEvidence}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                allowResumeEvidence: event.target.checked,
              }))
            }
          />
          Use indexed résumé evidence
        </label>
      </div>

      <h3>Paid-provider budget</h3>
      <div className="form-grid">
        <label>
          <span>Monthly maximum (USD)</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={settings.monthlyBudgetUsd}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                monthlyBudgetUsd: Number(event.target.value),
              }))
            }
          />
          <small>
            $0 blocks paid-provider generation; local Ollama can still be used
            when configured.
          </small>
        </label>
        <label>
          <span>Warning threshold (USD)</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={settings.warningBudgetUsd}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                warningBudgetUsd: Number(event.target.value),
              }))
            }
          />
        </label>
        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.hardStop}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                hardStop: event.target.checked,
              }))
            }
          />
          Hard stop paid generation when projected spend exceeds maximum
        </label>
      </div>

      {status && (
        <>
          <div className="metrics">
            <article>
              <strong>{money(status.usage.spentUsd)}</strong>
              <span>paid spend</span>
            </article>
            <article>
              <strong>{money(status.usage.reservedUsd)}</strong>
              <span>reserved</span>
            </article>
            <article>
              <strong>{status.usage.requestCount}</strong>
              <span>provider runs</span>
            </article>
          </div>
          <label>
            <span>
              Paid usage · {money(status.usage.projectedUsd)} projected ·{" "}
              {money(status.usage.remainingUsd)} remaining
            </span>
            <progress max={100} value={budgetPercent} />
          </label>
        </>
      )}

      <h3>Writing preference learning</h3>
      <div className="cloud-connection">
        <strong>{style?.samples ?? 0} approved owner edits learned</strong>
        <span>
          {style?.instructions ??
            "MUNSHI will learn style only from generated drafts that you edit and explicitly approve."}
        </span>
      </div>

      <h3>Pricing gate</h3>
      {status?.pricing ? (
        <div className="cloud-connection">
          <strong>{status.pricing.model}</strong>
          <span>
            {money(status.pricing.inputUsdPerMillionTokens)} input / 1M ·{" "}
            {money(status.pricing.outputUsdPerMillionTokens)} output / 1M
          </span>
          {status.pricing.stale && (
            <span className="diagnostic-error">
              Pricing is stale; paid generation remains blocked until
              re-verified.
            </span>
          )}
        </div>
      ) : settings.provider === "ollama" ? (
        <div className="cloud-connection">
          <strong>Local provider selected</strong>
          <span>
            Ollama runs on loopback and does not use the paid-provider budget.
          </span>
        </div>
      ) : (
        <div className="safety-callout">
          <strong>
            No verified pricing for the current OpenAI routine model
          </strong>
          <span>
            Paid generation will not run without a known current pricing
            snapshot. Local fallback can remain available.
          </span>
        </div>
      )}

      <div className="record-actions">
        <button
          className="primary"
          type="button"
          disabled={busy}
          onClick={() => void saveControls()}
        >
          Save AI controls
        </button>
        <button
          className="quiet"
          type="button"
          disabled={busy}
          onClick={() => void refresh()}
        >
          Refresh status
        </button>
      </div>
      {message && (
        <div className={messageIsError ? "diagnostic-error" : "notice"}>
          {message}
        </div>
      )}

      <div className="safety-callout">
        <strong>Truth boundary, not a usability barrier</strong>
        <span>
          Generated answers can cover job-specific narrative questions using job
          context plus verified candidate evidence. Work authorization,
          sponsorship, EEO/demographics, factual disclosures, security
          checkpoints, and final submission are not invented by AI. Every
          generated answer remains reviewable and must be approved before
          guarded fill.
        </span>
      </div>
    </section>
  );
}
