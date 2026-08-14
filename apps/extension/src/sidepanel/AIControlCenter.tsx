import { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteOpenAIKey,
  getAIControlStatus,
  listOpenAIModels,
  saveAISettings,
  setOpenAIKey,
  testOpenAIConnection,
  type AIControlStatus,
  type AISettings,
} from "../messaging/native";

const defaultSettings: AISettings = {
  provider: "openai",
  enabled: false,
  model: "",
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

export function AIControlCenter({ nativeAvailable }: { nativeAvailable: boolean }) {
  const [status, setStatus] = useState<AIControlStatus | null>(null);
  const [settings, setSettings] = useState<AISettings>(defaultSettings);
  const [models, setModels] = useState<string[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    if (!nativeAvailable) return;
    const next = await getAIControlStatus();
    setStatus(next);
    setSettings(next.settings);
  }, [nativeAvailable]);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
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

  async function storeKey(): Promise<void> {
    if (!apiKey.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      await setOpenAIKey(apiKey.trim());
      setApiKey("");
      await refresh();
      setMessage(
        "OpenAI credential stored in macOS Keychain. The saved secret is never displayed by MUNSHI.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to store API key");
    } finally {
      setBusy(false);
    }
  }

  async function removeKey(): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await deleteOpenAIKey();
      setModels([]);
      await refresh();
      setMessage("Stored OpenAI credential removed from macOS Keychain.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to delete API key");
    } finally {
      setBusy(false);
    }
  }

  async function testConnection(): Promise<void> {
    setBusy(true);
    setMessage("Testing OpenAI connection…");
    try {
      const connection = await testOpenAIConnection();
      const availableModels = await listOpenAIModels();
      setModels(availableModels);
      setMessage(
        `OpenAI connection verified. ${connection.modelCount} models are visible to this credential. No generation request was made.`,
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "OpenAI connection test failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveControls(): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const saved = await saveAISettings(settings);
      setSettings(saved);
      await refresh();
      setMessage("AI permissions and spending controls saved locally.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Unable to save AI controls",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!nativeAvailable) {
    return (
      <section>
        <p className="eyebrow">Owner-controlled intelligence</p>
        <h2>AI Control Center</h2>
        <div className="safety-callout">
          <strong>Native companion required</strong>
          <span>
            API credentials and paid-AI enforcement live in the local native
            companion. No browser-only fallback stores or uses your API key.
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
        <span className={settings.keyConfigured ? "badge" : "badge review"}>
          {settings.keyConfigured ? "Keychain connected" : "Not connected"}
        </span>
      </div>

      <p>
        You control the provider, permissions, and budget. Connecting OpenAI does
        not let MUNSHI invent facts or silently approve generated answers.
      </p>

      <h3>OpenAI connection</h3>
      <div className="cloud-pairing">
        <p>
          Saved credential: {settings.keyConfigured ? "•••••••• · secured" : "none"}
          {settings.keyConfigured ? ` · ${settings.keySource}` : ""}
        </p>
        <label>
          <span>{settings.keyConfigured ? "Replace API key" : "OpenAI API key"}</span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={apiKey}
            placeholder="Paste key on your Mac"
            onChange={(event) => setApiKey(event.target.value)}
          />
        </label>
        <button
          className="primary"
          type="button"
          disabled={busy || !apiKey.trim()}
          onClick={() => void storeKey()}
        >
          {settings.keyConfigured ? "Replace Keychain key" : "Store in macOS Keychain"}
        </button>
        <button
          className="quiet"
          type="button"
          disabled={busy || !settings.keyConfigured}
          onClick={() => void testConnection()}
        >
          Test connection & load models
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

      <h3>Model & permissions</h3>
      <div className="form-grid">
        <label>
          <span>Selected model</span>
          <input
            type="text"
            list="munshi-ai-models"
            value={settings.model}
            placeholder="Test connection, then select a priced model"
            onChange={(event) =>
              setSettings((current) => ({ ...current, model: event.target.value }))
            }
          />
          <datalist id="munshi-ai-models">
            {models.map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
        </label>
        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.enabled}
            onChange={(event) =>
              setSettings((current) => ({ ...current, enabled: event.target.checked }))
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
          Allow verified profile evidence
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
          Allow verified résumé evidence
        </label>
      </div>

      <h3>Spending controls</h3>
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
          <small>$0 means no paid provider request is authorized.</small>
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
              setSettings((current) => ({ ...current, hardStop: event.target.checked }))
            }
          />
          Hard stop when projected spend exceeds the monthly maximum
        </label>
      </div>

      {status && (
        <>
          <div className="metrics">
            <article>
              <strong>{money(status.usage.spentUsd)}</strong>
              <span>spent this month</span>
            </article>
            <article>
              <strong>{money(status.usage.reservedUsd)}</strong>
              <span>reserved</span>
            </article>
            <article>
              <strong>{status.usage.requestCount}</strong>
              <span>requests</span>
            </article>
          </div>
          <label>
            <span>
              Monthly usage · {money(status.usage.projectedUsd)} projected · {money(status.usage.remainingUsd)} remaining
            </span>
            <progress max={100} value={budgetPercent} />
          </label>
          <p>
            {status.usage.inputTokens.toLocaleString()} input tokens ·{" "}
            {status.usage.outputTokens.toLocaleString()} output tokens
          </p>
          {status.usage.estimatedCostUsd > 0 && (
            <p className="diagnostic-error">
              {money(status.usage.estimatedCostUsd)} is conservatively estimated
              from provider failures where exact billable usage could not be
              confirmed.
            </p>
          )}
        </>
      )}

      <h3>Pricing gate</h3>
      {status?.pricing ? (
        <div className="cloud-connection">
          <strong>{status.pricing.model}</strong>
          <span>
            {money(status.pricing.inputUsdPerMillionTokens)} input / 1M ·{" "}
            {money(status.pricing.outputUsdPerMillionTokens)} output / 1M
          </span>
          <span>
            Pricing verified {new Date(status.pricing.verifiedAt).toLocaleDateString()} · age {status.pricing.ageDays} days
          </span>
          {status.pricing.stale && (
            <span className="diagnostic-error">
              Pricing snapshot is stale. Native enforcement will block paid
              generation until it is re-verified.
            </span>
          )}
        </div>
      ) : (
        <div className="safety-callout">
          <strong>No verified pricing for selected model</strong>
          <span>
            MUNSHI will not make a paid generation request with an unpriced model.
          </span>
        </div>
      )}

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
        Refresh usage
      </button>
      {message && <div className="notice">{message}</div>}

      <div className="safety-callout">
        <strong>Permanent truth boundary</strong>
        <span>
          AI drafting is limited to selected narrative question types and
          authoritative non-protected evidence. Work authorization, sponsorship,
          salary, EEO/demographics, disclosures, security checks, and final
          submission remain outside autonomous AI generation. Every generated
          answer remains a draft requiring owner review.
        </span>
      </div>
    </section>
  );
}
