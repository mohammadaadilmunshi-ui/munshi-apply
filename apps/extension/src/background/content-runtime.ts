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

type ContentScanResponse = {
  ok?: boolean;
  error?: string;
};

export function isMissingContentReceiverError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return /could not establish connection|receiving end does not exist|message port closed|message channel closed|extension context invalidated|context invalidated/i.test(
    message,
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
): Promise<T> {
  try {
    return await api.sendMessage<T>(tabId, message, { frameId });
  } catch (error) {
    if (!isMissingContentReceiverError(error)) throw error;
  }

  await api.executeScript({
    target: { tabId, frameIds: [frameId] },
    files: [CONTENT_SCRIPT_FILE],
  });
  return api.sendMessage<T>(tabId, message, { frameId });
}

export async function ensureTabContentRuntime(
  api: ContentRuntimeApi,
  tabId: number,
): Promise<void> {
  let topFrameHealthy = false;
  try {
    await api.sendMessage(tabId, { type: "CONTENT_PING" }, { frameId: 0 });
    topFrameHealthy = true;
  } catch (error) {
    if (!isMissingContentReceiverError(error)) throw error;
  }

  let framesToScan = [0];
  try {
    const injected = await api.executeScript({
      target: { tabId, allFrames: true },
      files: [CONTENT_SCRIPT_FILE],
    });
    framesToScan = [...new Set([0, ...injectedFrameIds(injected)])];
  } catch (error) {
    if (!topFrameHealthy) {
      await api.executeScript({
        target: { tabId, frameIds: [0] },
        files: [CONTENT_SCRIPT_FILE],
      });
    }
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
