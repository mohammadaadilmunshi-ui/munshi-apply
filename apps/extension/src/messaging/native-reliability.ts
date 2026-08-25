const nativeHostName = "systems.munshi.apply";
const TRANSPORT_STATUS_KEY = "native-transport-status-v1";

type NativeResponse =
  | { ok: true; data?: unknown }
  | { ok: false; error: string };

export type NativeTransportStatus = {
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  lastError: string | null;
  consecutiveFailures: number;
};

export type LearnedInteractionLesson = {
  recipeId: string;
  siteOrigin: string;
  semanticType: string;
  state: "SHADOW" | "PROMOTED" | "ROLLED_BACK";
  version: number;
  verifiedAttempts: number;
  verifiedSuccesses: number;
  actionCount: number;
  createdAt: string;
  updatedAt: string;
};

const emptyTransportStatus: NativeTransportStatus = {
  lastSuccessAt: null,
  lastFailureAt: null,
  lastError: null,
  consecutiveFailures: 0,
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? "Native companion failed");
}

function retryableNativeError(error: unknown): boolean {
  return /timed out|message port closed|native messaging host.*exited|communication with.*native|disconnected|broken pipe|connection.*closed/i.test(
    errorMessage(error),
  );
}

async function loadTransportStatus(): Promise<NativeTransportStatus> {
  try {
    const stored = await chrome.storage.session.get(TRANSPORT_STATUS_KEY);
    const candidate = stored[TRANSPORT_STATUS_KEY] as
      | Partial<NativeTransportStatus>
      | undefined;
    return {
      lastSuccessAt:
        typeof candidate?.lastSuccessAt === "string"
          ? candidate.lastSuccessAt
          : null,
      lastFailureAt:
        typeof candidate?.lastFailureAt === "string"
          ? candidate.lastFailureAt
          : null,
      lastError:
        typeof candidate?.lastError === "string" ? candidate.lastError : null,
      consecutiveFailures: Number.isSafeInteger(candidate?.consecutiveFailures)
        ? Number(candidate?.consecutiveFailures)
        : 0,
    };
  } catch {
    return { ...emptyTransportStatus };
  }
}

async function saveTransportStatus(status: NativeTransportStatus): Promise<void> {
  try {
    await chrome.storage.session.set({ [TRANSPORT_STATUS_KEY]: status });
  } catch {
    // Health telemetry must never make the native request fail.
  }
}

async function recordSuccess(): Promise<void> {
  const current = await loadTransportStatus();
  await saveTransportStatus({
    ...current,
    lastSuccessAt: new Date().toISOString(),
    lastError: null,
    consecutiveFailures: 0,
  });
}

async function recordFailure(error: unknown): Promise<void> {
  const current = await loadTransportStatus();
  await saveTransportStatus({
    ...current,
    lastFailureAt: new Date().toISOString(),
    lastError: errorMessage(error),
    consecutiveFailures: current.consecutiveFailures + 1,
  });
}

function sendNativeOnce<T>(
  message: Record<string, unknown>,
  timeoutMilliseconds: number,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(nativeHostName);
    let settled = false;
    const finish = (callback: () => void): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      try {
        port.disconnect();
      } catch {
        // Port may already be gone after a transient host exit.
      }
      callback();
    };
    const timeout = setTimeout(() => {
      finish(() => reject(new Error("Native companion request timed out")));
    }, timeoutMilliseconds);

    port.onMessage.addListener((response: NativeResponse) => {
      if (!response.ok) {
        finish(() => reject(new Error(response.error)));
        return;
      }
      finish(() => resolve(response.data as T));
    });
    port.onDisconnect.addListener(() => {
      if (settled) return;
      const lastError = chrome.runtime.lastError;
      finish(() =>
        reject(
          new Error(lastError?.message || "Native companion disconnected unexpectedly"),
        ),
      );
    });
    port.postMessage(message);
  });
}

async function wait(milliseconds: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function sendNativeWithRecovery<T>(
  message: Record<string, unknown>,
  options: {
    timeoutMilliseconds?: number;
    attempts?: number;
  } = {},
): Promise<T> {
  const timeoutMilliseconds = Math.max(250, options.timeoutMilliseconds ?? 3_000);
  const attempts = Math.max(1, Math.min(4, options.attempts ?? 3));
  let lastError: unknown = new Error("Native companion request failed");
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const result = await sendNativeOnce<T>(message, timeoutMilliseconds);
      await recordSuccess();
      return result;
    } catch (error) {
      lastError = error;
      if (!retryableNativeError(error) || attempt === attempts) break;
      await wait(125 * attempt);
    }
  }
  await recordFailure(lastError);
  throw lastError;
}

export async function getNativeHealthWithRecovery(): Promise<
  Record<string, unknown>
> {
  const health = await sendNativeWithRecovery<Record<string, unknown>>(
    { type: "PING" },
    { timeoutMilliseconds: 3_000, attempts: 3 },
  );
  return {
    ...health,
    transport: await loadTransportStatus(),
  };
}

function parseLesson(value: unknown): LearnedInteractionLesson | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Record<string, unknown>;
  const state = candidate.state;
  if (state !== "SHADOW" && state !== "PROMOTED" && state !== "ROLLED_BACK") {
    return null;
  }
  const strings = [
    candidate.recipeId,
    candidate.siteOrigin,
    candidate.semanticType,
    candidate.createdAt,
    candidate.updatedAt,
  ];
  if (!strings.every((item) => typeof item === "string" && item.trim())) return null;
  const integers = [
    candidate.version,
    candidate.verifiedAttempts,
    candidate.verifiedSuccesses,
    candidate.actionCount,
  ];
  if (!integers.every((item) => Number.isSafeInteger(item) && Number(item) >= 0)) {
    return null;
  }
  return {
    recipeId: String(candidate.recipeId),
    siteOrigin: String(candidate.siteOrigin),
    semanticType: String(candidate.semanticType),
    state,
    version: Number(candidate.version),
    verifiedAttempts: Number(candidate.verifiedAttempts),
    verifiedSuccesses: Number(candidate.verifiedSuccesses),
    actionCount: Number(candidate.actionCount),
    createdAt: String(candidate.createdAt),
    updatedAt: String(candidate.updatedAt),
  };
}

export async function listNativeInteractionLessons(): Promise<
  LearnedInteractionLesson[]
> {
  const raw = await sendNativeWithRecovery<unknown>(
    { type: "LIST_INTERACTION_RECIPES" },
    { timeoutMilliseconds: 4_000, attempts: 2 },
  );
  if (!Array.isArray(raw)) throw new Error("Native lesson list is invalid");
  return raw.map(parseLesson).filter((item): item is LearnedInteractionLesson => item !== null);
}

export async function getNativeTransportStatus(): Promise<NativeTransportStatus> {
  return loadTransportStatus();
}
