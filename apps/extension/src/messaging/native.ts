const nativeHostName = "systems.munshi.apply";

type NativeResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };

export async function getNativeHealth(
  timeoutMilliseconds = 3_000,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(nativeHostName);
    const timeout = setTimeout(() => {
      port.disconnect();
      reject(new Error("Native companion health check timed out"));
    }, timeoutMilliseconds);

    port.onMessage.addListener((message: NativeResponse) => {
      clearTimeout(timeout);
      port.disconnect();
      if (!message.ok) {
        reject(new Error(message.error));
        return;
      }
      resolve(message.data);
    });
    port.onDisconnect.addListener(() => {
      const lastError = chrome.runtime.lastError;
      if (!lastError) return;
      clearTimeout(timeout);
      reject(new Error(lastError.message));
    });
    port.postMessage({ type: "PING" });
  });
}
