import {
  recoverHistoryStateChange,
  type HistoryStateRecoveryDependencies,
} from "./history-state-recovery";
import { clearPagesForTab, deletePage, getPagesForTab } from "../storage/vault";

export type ContentRuntimeApi = {
  sendMessage<T>(
    tabId: number,
    message: unknown,
    options: { frameId: number },
  ): Promise<T>;
  executeScript(details: {
    target: { tabId: number; frameIds?: number[]; allFrames?: boolean };
    files: string[];
  }): Promise<unknown>;
};

const CONTENT_SCRIPT_FILE = "content/bootstrap.js";
export const DEFAULT_CONTENT_MESSAGE_TIMEOUT_MS = 10_000;

type ContentScanResponse = {
  ok?: boolean;
  error?: string;
};

type ContentRecoveryOptions = {
  timeoutMs?: number;
};

let historyStateRecoveryInstalled = false;

export function isMissingContentReceiverError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return /could not establish connection|receiving end does not exist|message port closed|message channel closed|extension context invalidated|context invalidated|content message timed out/i.test(
    message,
  );
}

async function withContentMessageTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Content message timed out after ${timeoutMs}ms`));
    }, timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

function sendMessageWithTimeout<T>(
  api: ContentRuntimeApi,
  tabId: number,
  frameId: number,
  message: unknown,
  timeoutMs: number,
): Promise<T> {
  return withContentMessageTimeout(
    api.sendMessage<T>(tabId, message, { frameId }),
    timeoutMs,
  );
}

function injectedFrameIds(result: unknown): number[] {
  if (!Array.isArray(result)) return [];
  return result
    .map((entry) =>
      entry && typeof entry === "object" && "frameId" in entry
        ? Number((entry as { frameId?: unknown }).frameId)
        : Number.NaN,
    )
    .filter((frameId) => Number.isSafeInteger(frameId) && frameId >= 0);
}

function assertSuccessfulScan(
  response: ContentScanResponse | undefined,
  frameId: number,
): void {
  if (response?.ok === true) return;
  throw new Error(
    response?.error || `Content scan did not complete for frame ${frameId}`,
  );
}

export async function sendWithContentRecovery<T>(
  api: ContentRuntimeApi,
  tabId: number,
  frameId: number,
  message: unknown,
  options: ContentRecoveryOptions = {},
): Promise<T> {
  const timeoutMs = Math.max(
    1,
    options.timeoutMs ?? DEFAULT_CONTENT_MESSAGE_TIMEOUT_MS,
  );
  try {
    return await sendMessageWithTimeout<T>(
      api,
      tabId,
      frameId,
      message,
      timeoutMs,
    );
  } catch (error) {
    if (!isMissingContentReceiverError(error)) throw error;
  }

  await api.executeScript({
    target: { tabId, frameIds: [frameId] },
    files: [CONTENT_SCRIPT_FILE],
  });
  return sendMessageWithTimeout<T>(api, tabId, frameId, message, timeoutMs);
}

function installHistoryStateRecovery(api: ContentRuntimeApi): void {
  if (historyStateRecoveryInstalled) return;
  if (
    typeof chrome === "undefined" ||
    !chrome.webNavigation?.onHistoryStateUpdated
  ) {
    return;
  }

  const dependencies: HistoryStateRecoveryDependencies = {
    getPages: getPagesForTab,
    clearTab: clearPagesForTab,
    deleteFrame: deletePage,
    scanFrame: async (tabId, frameId) => {
      const response = await sendWithContentRecovery<ContentScanResponse>(
        api,
        tabId,
        frameId,
        { type: "CONTENT_SCAN_NOW" },
      );
      assertSuccessfulScan(response, frameId);
    },
  };

  chrome.webNavigation.onHistoryStateUpdated.addListener((details) => {
    if (details.tabId < 0) return;
    void recoverHistoryStateChange(
      details.tabId,
      details.frameId,
      dependencies,
    ).catch(() => undefined);
  });
  historyStateRecoveryInstalled = true;
}

export async function ensureTabContentRuntime(
  api: ContentRuntimeApi,
  tabId: number,
): Promise<void> {
  installHistoryStateRecovery(api);
  let topFrameHealthy = false;
  try {
    await sendMessageWithTimeout(
      api,
      tabId,
      0,
      { type: "CONTENT_PING" },
      DEFAULT_CONTENT_MESSAGE_TIMEOUT_MS,
    );
    topFrameHealthy = true;
  } catch (error) {
    if (!isMissingContentReceiverError(error)) throw error;
  }

  if (topFrameHealthy) {
    const response = await sendWithContentRecovery<ContentScanResponse>(
      api,
      tabId,
      0,
      { type: "CONTENT_SCAN_NOW" },
    );
    assertSuccessfulScan(response, 0);
    return;
  }

  let framesToScan = [0];
  try {
    const injected = await api.executeScript({
      target: { tabId, allFrames: true },
      files: [CONTENT_SCRIPT_FILE],
    });
    framesToScan = [...new Set([0, ...injectedFrameIds(injected)])];
  } catch {
    await api.executeScript({
      target: { tabId, frameIds: [0] },
      files: [CONTENT_SCRIPT_FILE],
    });
    framesToScan = [0];
  }

  for (const frameId of framesToScan) {
    try {
      const response = await sendWithContentRecovery<ContentScanResponse>(
        api,
        tabId,
        frameId,
        { type: "CONTENT_SCAN_NOW" },
      );
      assertSuccessfulScan(response, frameId);
    } catch (error) {
      if (frameId === 0) throw error;
    }
  }
}
