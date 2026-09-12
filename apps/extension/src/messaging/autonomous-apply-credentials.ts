import { createNativeRequestBroker } from "./native-transport";

const nativeHostName = "systems.munshi.apply";
const broker = createNativeRequestBroker({
  connect: () => chrome.runtime.connectNative(nativeHostName),
  getLastErrorMessage: () => chrome.runtime.lastError?.message,
  idleDisconnectMilliseconds: 2_000,
});

export type AutonomousApplyAuthMode = "subscription" | "api";
export type CredentialSource = "keychain" | "environment" | "none";

export type AutonomousApplySettings = {
  enabled: boolean;
  authMode: AutonomousApplyAuthMode;
  model: string;
  headless: boolean;
  maxTurns: number;
  maxCostPerApplicationUsd: number;
  allowFinalSubmit: boolean;
  challengeServiceEnabled: boolean;
  anthropicKeyConfigured: boolean;
  anthropicKeySource: CredentialSource;
  capSolverKeyConfigured: boolean;
  capSolverKeySource: CredentialSource;
};

export type AutonomousApplyRuntimeStatus = AutonomousApplySettings & {
  claudeCliInstalled: boolean;
  claudeCliPath: string | null;
  playwrightLauncherInstalled: boolean;
  npxPath: string | null;
  credentialReady: boolean;
  readyForDryRun: boolean;
};

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

async function sendNative<T>(
  message: Record<string, unknown>,
  timeoutMilliseconds = 10_000,
): Promise<T> {
  return broker.request<T>(message, timeoutMilliseconds);
}

function parseSource(value: unknown): CredentialSource {
  return value === "keychain" || value === "environment" ? value : "none";
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : fallback;
}

export function parseAutonomousApplySettings(
  value: unknown,
): AutonomousApplySettings {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Autonomous apply settings are invalid");
  }
  const candidate = value as Record<string, unknown>;
  const authMode = candidate.authMode === "api" ? "api" : "subscription";
  const model =
    typeof candidate.model === "string" && candidate.model.trim()
      ? candidate.model.trim()
      : defaults.model;
  return {
    enabled: candidate.enabled === true,
    authMode,
    model,
    headless: candidate.headless === true,
    maxTurns: Math.max(1, Math.trunc(finiteNumber(candidate.maxTurns, 40))),
    maxCostPerApplicationUsd: finiteNumber(
      candidate.maxCostPerApplicationUsd,
      1,
    ),
    allowFinalSubmit: candidate.allowFinalSubmit === true,
    challengeServiceEnabled: candidate.challengeServiceEnabled === true,
    anthropicKeyConfigured: candidate.anthropicKeyConfigured === true,
    anthropicKeySource: parseSource(candidate.anthropicKeySource),
    capSolverKeyConfigured: candidate.capSolverKeyConfigured === true,
    capSolverKeySource: parseSource(candidate.capSolverKeySource),
  };
}

export async function getAutonomousApplySettings(): Promise<AutonomousApplySettings> {
  return parseAutonomousApplySettings(
    await sendNative<unknown>({ type: "GET_AUTONOMOUS_APPLY_SETTINGS" }),
  );
}

export async function saveAutonomousApplySettings(
  settings: AutonomousApplySettings,
): Promise<AutonomousApplySettings> {
  return parseAutonomousApplySettings(
    await sendNative<unknown>({
      type: "SAVE_AUTONOMOUS_APPLY_SETTINGS",
      payload: {
        enabled: settings.enabled,
        authMode: settings.authMode,
        model: settings.model,
        headless: settings.headless,
        maxTurns: settings.maxTurns,
        maxCostPerApplicationUsd: settings.maxCostPerApplicationUsd,
        allowFinalSubmit: settings.allowFinalSubmit,
        challengeServiceEnabled: settings.challengeServiceEnabled,
      },
    }),
  );
}

export async function setAnthropicApiKey(
  apiKey: string,
): Promise<AutonomousApplySettings> {
  return parseAutonomousApplySettings(
    await sendNative<unknown>({
      type: "SET_ANTHROPIC_API_KEY",
      payload: { apiKey },
    }),
  );
}

export async function deleteAnthropicApiKey(): Promise<AutonomousApplySettings> {
  return parseAutonomousApplySettings(
    await sendNative<unknown>({ type: "DELETE_ANTHROPIC_API_KEY" }),
  );
}

export async function setCapSolverApiKey(
  apiKey: string,
): Promise<AutonomousApplySettings> {
  return parseAutonomousApplySettings(
    await sendNative<unknown>({
      type: "SET_CAPSOLVER_API_KEY",
      payload: { apiKey },
    }),
  );
}

export async function deleteCapSolverApiKey(): Promise<AutonomousApplySettings> {
  return parseAutonomousApplySettings(
    await sendNative<unknown>({ type: "DELETE_CAPSOLVER_API_KEY" }),
  );
}

export async function getAutonomousApplyRuntimeStatus(): Promise<AutonomousApplyRuntimeStatus> {
  const raw = await sendNative<Record<string, unknown>>({
    type: "GET_AUTONOMOUS_APPLY_RUNTIME",
  });
  const settings = parseAutonomousApplySettings(raw);
  return {
    ...settings,
    claudeCliInstalled: raw.claudeCliInstalled === true,
    claudeCliPath:
      typeof raw.claudeCliPath === "string" ? raw.claudeCliPath : null,
    playwrightLauncherInstalled: raw.playwrightLauncherInstalled === true,
    npxPath: typeof raw.npxPath === "string" ? raw.npxPath : null,
    credentialReady: raw.credentialReady === true,
    readyForDryRun: raw.readyForDryRun === true,
  };
}
