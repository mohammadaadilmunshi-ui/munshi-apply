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

export function isMissingContentReceiverError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return /could not establish connection|receiving end does not exist/i.test(
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
  let framesToScan = [0];
  try {
    await api.sendMessage(tabId, { type: "CONTENT_PING" }, { frameId: 0 });
  } catch (error) {
    if (!isMissingContentReceiverError(error)) throw error;
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
  }

  for (const frameId of framesToScan) {
    try {
      await sendWithContentRecovery(api, tabId, frameId, {
        type: "CONTENT_SCAN_NOW",
      });
    } catch (error) {
      if (frameId === 0) throw error;
    }
  }
}
