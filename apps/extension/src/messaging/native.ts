import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";

const nativeHostName = "systems.munshi.apply";

type NativeResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };

export type AISettings = {
  provider: "openai";
  enabled: boolean;
  model: string;
  monthlyBudgetUsd: number;
  warningBudgetUsd: number;
  hardStop: boolean;
  keyConfigured: boolean;
  keySource: "keychain" | "environment" | "none";
};

async function sendNative<T>(
  message: Record<string, unknown>,
  timeoutMilliseconds = 10_000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(nativeHostName);
    const timeout = setTimeout(() => {
      port.disconnect();
      reject(new Error("Native companion request timed out"));
    }, timeoutMilliseconds);

    port.onMessage.addListener((response: NativeResponse) => {
      clearTimeout(timeout);
      port.disconnect();
      if (!response.ok) {
        reject(
          new Error(
            "error" in response ? response.error : "Native companion failed",
          ),
        );
        return;
      }
      resolve(response.data as T);
    });
    port.onDisconnect.addListener(() => {
      const lastError = chrome.runtime.lastError;
      if (!lastError) return;
      clearTimeout(timeout);
      reject(new Error(lastError.message));
    });
    port.postMessage(message);
  });
}

export async function getNativeHealth(
  timeoutMilliseconds = 3_000,
): Promise<unknown> {
  return sendNative({ type: "PING" }, timeoutMilliseconds);
}

export async function getNativeProfileSnapshot(): Promise<ProfileSnapshot | null> {
  const candidate = await sendNative<unknown>({
    type: "GET_PROFILE_SNAPSHOT",
  });
  return candidate === null ? null : parseProfileSnapshot(candidate);
}

export async function saveNativeProfileSnapshot(
  snapshot: ProfileSnapshot,
): Promise<void> {
  await sendNative({
    type: "SAVE_PROFILE_SNAPSHOT",
    payload: parseProfileSnapshot(snapshot),
  });
}

export async function getAISettings(): Promise<AISettings> {
  return sendNative<AISettings>({ type: "GET_AI_SETTINGS" });
}

export async function saveAISettings(
  settings: AISettings,
): Promise<AISettings> {
  return sendNative<AISettings>({
    type: "SAVE_AI_SETTINGS",
    payload: {
      provider: settings.provider,
      enabled: settings.enabled,
      model: settings.model,
      monthlyBudgetUsd: settings.monthlyBudgetUsd,
      warningBudgetUsd: settings.warningBudgetUsd,
      hardStop: settings.hardStop,
    },
  });
}

export async function setOpenAIKey(apiKey: string): Promise<AISettings> {
  return sendNative<AISettings>({
    type: "SET_OPENAI_API_KEY",
    payload: { apiKey },
  });
}

export async function deleteOpenAIKey(): Promise<AISettings> {
  return sendNative<AISettings>({ type: "DELETE_OPENAI_API_KEY" });
}

export async function testOpenAIConnection(): Promise<{ modelCount: number }> {
  return sendNative<{ modelCount: number }>(
    { type: "TEST_OPENAI_CONNECTION" },
    15_000,
  );
}

export async function listOpenAIModels(): Promise<string[]> {
  const result = await sendNative<{ models: string[] }>(
    { type: "LIST_OPENAI_MODELS" },
    15_000,
  );
  return result.models;
}
