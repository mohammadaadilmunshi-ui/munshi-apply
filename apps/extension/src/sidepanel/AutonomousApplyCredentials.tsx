import { useCallback, useEffect, useState } from "react";
import {
  deleteAnthropicApiKey,
  deleteCapSolverApiKey,
  getAutonomousApplyRuntimeStatus,
  saveAutonomousApplySettings,
  setAnthropicApiKey,
  setCapSolverApiKey,
  type AutonomousApplyRuntimeStatus,
  type AutonomousApplySettings,
} from "../messaging/autonomous-apply-credentials";

const defaults: AutonomousApplySettings = {
  enabled: false,
  authMode: "subscription",
  model: "sonnet",
  headless: false,
  maxTurns: 40,
  maxCostPerApplicationUsd: 1,
  allowFinalSubmit: false,
  challengeServiceEnabled: false,
  anthropicKeyConfigured: false,
  anthropicKeySource: "none",
  capSolverKeyConfigured: false,
  capSolverKeySource: "none",
};

export function AutonomousApplyCredentials() {
  const [settings, setSettings] =
    useState<AutonomousApplySettings>(defaults);
  const [runtime, setRuntime] =
    useState<AutonomousApplyRuntimeStatus | null>(null);
  const [anthropicKey, setAnthropicKey] = useState("");
  const [capSolverKey, setCapSolverKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    const next = await getAutonomousApplyRuntimeStatus();
    setRuntime(next);
    setSettings(next);
  }, []);

  useEffect(() => {
    void refresh().catch((cause: unknown) => {
      setError(true);
      setMessage(
        cause instanceof Error
          ? cause.message
          : "Unable to load autonomous apply credentials",
      );
    });
  }, [refresh]);

  async function run(action: () => Promise<void>): Promise<void> {
    setBusy(true);
    setError(false);
    setMessage("");
    try {
      await action();
    } catch (cause) {
      setError(true);
      setMessage(
        cause instanceof Error ? cause.message : "Credential action failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings(): Promise<void> {
    await run(async () => {
      const saved = await saveAutonomousApplySettings(settings);
      setSettings(saved);
      await refresh();
      setMessage("Autonomous apply settings saved locally.");
    });
  }

  async function storeAnthropicKey(): Promise<void> {
    if (!anthropicKey.trim()) return;
    await run(async () => {
      const saved = await setAnthropicApiKey(anthropicKey.trim());
      setSettings(saved);
      setAnthropicKey("");
      await refresh();
      setMessage("Anthropic API key stored in macOS Keychain.");
    });
  }

  async function removeAnthropicKey(): Promise<void> {
    await run(async () => {
      const saved = await deleteAnthropicApiKey();
      setSettings(saved);
      await refresh();
      setMessage("Anthropic API key removed from macOS Keychain.");
    });
  }

  async function storeCapSolverKey(): Promise<void> {
    if (!capSolverKey.trim()) return;
    await run(async () => {
      const saved = await setCapSolverApiKey(capSolverKey.trim());
      setSettings(saved);
      setCapSolverKey("");
      await refresh();
      setMessage(
        "Optional challenge-service credential stored in macOS Keychain.",
      );
    });
  }

  async function removeCapSolverKey(): Promise<void> {
    await run(async () => {
      const saved = await deleteCapSolverApiKey();
      setSettings(saved);
      await refresh();
      setMessage("Optional challenge-service credential removed.");
    });
  }

  const anthropicStatus =
    settings.authMode === "subscription"
      ? "Not required in subscription mode. Authenticate Claude Code on this Mac once."
      : settings.anthropicKeyConfigured
        ? `Saved: •••••••• · ${settings.anthropicKeySource}`
        : "No Anthropic API key configured.";

  const capSolverStatus = settings.capSolverKeyConfigured
    ? `•••••••• · ${settings.capSolverKeySource}`
    : "none";

  return (
    <div className="repeatable-profile">
      <div className="repeatable-intro">
        <p className="eyebrow">Apply-only runtime</p>
        <h3>Autonomous Apply Credentials</h3>
        <p>
          These credentials are only for the browser application executor. Job
          discovery, scoring, résumé generation, and cover letters continue to
          use MUNSHI&apos;s existing pipeline.
        </p>
      </div>

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
          Enable autonomous browser executor
        </label>

        <label>
          <span>Claude Code authentication</span>
          <select
            value={settings.authMode}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                authMode:
                  event.target.value === "api" ? "api" : "subscription",
              }))
            }
          >
            <option value="subscription">
              Claude subscription login · no API key stored
            </option>
            <option value="api">Anthropic API key · usage billed by API</option>
          </select>
        </label>

        <label>
          <span>Browser-agent model</span>
          <input
            type="text"
            value={settings.model}
            placeholder="sonnet"
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                model: event.target.value,
              }))
            }
          />
        </label>

        <label>
          <span>Maximum agent turns per application</span>
          <input
            type="number"
            min={1}
            max={200}
            step={1}
            value={settings.maxTurns}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                maxTurns: Number(event.target.value),
              }))
            }
          />
        </label>

        <label>
          <span>Maximum AI cost per application (USD)</span>
          <input
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={settings.maxCostPerApplicationUsd}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                maxCostPerApplicationUsd: Number(event.target.value),
              }))
            }
          />
        </label>

        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.headless}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                headless: event.target.checked,
              }))
            }
          />
          Run browser headless when supported
        </label>

        <label className="answer-approval">
          <input
            type="checkbox"
            checked={settings.allowFinalSubmit}
            onChange={(event) =>
              setSettings((current) => ({
                ...current,
                allowFinalSubmit: event.target.checked,
              }))
            }
          />
          Permit final submit when the Application Plan also authorizes it
        </label>
      </div>

      <h3>Anthropic API credential</h3>
      <div className="cloud-pairing">
        <p>{anthropicStatus}</p>
        <label>
          <span>
            {settings.anthropicKeyConfigured
              ? "Replace Anthropic API key"
              : "Anthropic API key"}
          </span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={anthropicKey}
            placeholder="Paste key on your Mac"
            onChange={(event) => setAnthropicKey(event.target.value)}
          />
        </label>
        <div className="record-actions">
          <button
            className="primary"
            type="button"
            disabled={busy || !anthropicKey.trim()}
            onClick={() => void storeAnthropicKey()}
          >
            Store in macOS Keychain
          </button>
          <button
            className="quiet destructive"
            type="button"
            disabled={busy || !settings.anthropicKeyConfigured}
            onClick={() => void removeAnthropicKey()}
          >
            Delete stored key
          </button>
        </div>
      </div>

      <h3>Optional challenge-service credential</h3>
      <div className="cloud-pairing">
        <p>
          ApplyPilot supports an optional third-party challenge service. MUNSHI
          stores the credential separately, but automatic challenge handling is
          disabled by default and security checkpoints remain visible to the
          owner.
        </p>
        <p>Saved credential: {capSolverStatus}</p>
        <label>
          <span>CapSolver API key · optional</span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={capSolverKey}
            placeholder="Optional"
            onChange={(event) => setCapSolverKey(event.target.value)}
          />
        </label>
        <div className="record-actions">
          <button
            className="quiet"
            type="button"
            disabled={busy || !capSolverKey.trim()}
            onClick={() => void storeCapSolverKey()}
          >
            Store optional key
          </button>
          <button
            className="quiet destructive"
            type="button"
            disabled={busy || !settings.capSolverKeyConfigured}
            onClick={() => void removeCapSolverKey()}
          >
            Delete optional key
          </button>
        </div>
      </div>

      <h3>Runtime readiness</h3>
      <div className="cloud-connection">
        <strong>
          {runtime?.readyForDryRun
            ? "Apply executor prerequisites detected"
            : "Apply executor setup incomplete"}
        </strong>
        <span>
          Claude Code: {runtime?.claudeCliInstalled ? "installed" : "missing"}
          {runtime?.claudeCliPath ? ` · ${runtime.claudeCliPath}` : ""}
        </span>
        <span>
          Playwright launcher:{" "}
          {runtime?.playwrightLauncherInstalled ? "available" : "missing"}
        </span>
        <span>
          Authentication:{" "}
          {runtime?.credentialReady ? "configured" : "needs setup"}
        </span>
      </div>

      <div className="record-actions">
        <button
          className="primary"
          type="button"
          disabled={busy}
          onClick={() => void saveSettings()}
        >
          Save autonomous apply settings
        </button>
        <button
          className="quiet"
          type="button"
          disabled={busy}
          onClick={() => void refresh()}
        >
          Refresh runtime status
        </button>
      </div>

      {message && (
        <div className={error ? "diagnostic-error" : "notice"}>{message}</div>
      )}
    </div>
  );
}
