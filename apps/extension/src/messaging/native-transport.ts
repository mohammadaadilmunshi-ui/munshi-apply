type NativeResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };

type QueuedRequest = {
  message: Record<string, unknown>;
  timeoutMilliseconds: number;
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
};

export type NativeRequestBroker = {
  request<T>(
    message: Record<string, unknown>,
    timeoutMilliseconds?: number,
  ): Promise<T>;
  dispose(): void;
};

export function createNativeRequestBroker(options: {
  connect: () => chrome.runtime.Port;
  getLastErrorMessage?: () => string | undefined;
  idleDisconnectMilliseconds?: number;
}): NativeRequestBroker {
  const queue: QueuedRequest[] = [];
  const idleDisconnectMilliseconds = Math.max(
    0,
    options.idleDisconnectMilliseconds ?? 2_000,
  );

  let port: chrome.runtime.Port | null = null;
  let active: QueuedRequest | null = null;
  let requestTimeout: ReturnType<typeof setTimeout> | null = null;
  let idleTimeout: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  const clearRequestTimeout = (): void => {
    if (requestTimeout !== null) clearTimeout(requestTimeout);
    requestTimeout = null;
  };

  const clearIdleTimeout = (): void => {
    if (idleTimeout !== null) clearTimeout(idleTimeout);
    idleTimeout = null;
  };

  const closePort = (): void => {
    clearIdleTimeout();
    const current = port;
    port = null;
    if (!current) return;
    try {
      current.disconnect();
    } catch {
      // The browser may already have closed the native port.
    }
  };

  const rejectQueued = (error: Error): void => {
    while (queue.length > 0) queue.shift()!.reject(error);
  };

  const scheduleIdleDisconnect = (): void => {
    clearIdleTimeout();
    if (disposed || active || queue.length > 0 || !port) return;
    idleTimeout = setTimeout(() => {
      idleTimeout = null;
      if (!active && queue.length === 0) closePort();
    }, idleDisconnectMilliseconds);
  };

  const pump = (): void => {
    if (disposed || active || queue.length === 0) {
      scheduleIdleDisconnect();
      return;
    }

    clearIdleTimeout();
    const next = queue.shift()!;
    active = next;

    if (!port) {
      try {
        const connected = options.connect();
        port = connected;

        connected.onMessage.addListener((response: NativeResponse) => {
          if (connected !== port || !active) return;
          const current = active;
          active = null;
          clearRequestTimeout();
          if (!response.ok) {
            current.reject(
              new Error(response.error || "Native companion failed"),
            );
          } else {
            current.resolve(response.data);
          }
          pump();
        });

        connected.onDisconnect.addListener(() => {
          if (connected !== port) return;
          port = null;
          clearIdleTimeout();
          clearRequestTimeout();
          if (active) {
            const current = active;
            active = null;
            current.reject(
              new Error(
                options.getLastErrorMessage?.() ||
                  "Native companion disconnected unexpectedly",
              ),
            );
          }
          pump();
        });
      } catch (error) {
        active = null;
        next.reject(
          error instanceof Error
            ? error
            : new Error("Native companion could not be started"),
        );
        pump();
        return;
      }
    }

    requestTimeout = setTimeout(() => {
      if (active !== next) return;
      active = null;
      requestTimeout = null;
      next.reject(new Error("Native companion request timed out"));
      closePort();
      pump();
    }, next.timeoutMilliseconds);

    try {
      port.postMessage(next.message);
    } catch (error) {
      if (active === next) active = null;
      clearRequestTimeout();
      next.reject(
        error instanceof Error
          ? error
          : new Error("Native companion request could not be sent"),
      );
      closePort();
      pump();
    }
  };

  return {
    request<T>(
      message: Record<string, unknown>,
      timeoutMilliseconds = 10_000,
    ): Promise<T> {
      if (disposed) {
        return Promise.reject(new Error("Native request broker is disposed"));
      }
      return new Promise<T>((resolve, reject) => {
        queue.push({
          message,
          timeoutMilliseconds: Math.max(1, timeoutMilliseconds),
          resolve: (value) => resolve(value as T),
          reject,
        });
        pump();
      });
    },
    dispose(): void {
      if (disposed) return;
      disposed = true;
      clearRequestTimeout();
      if (active) {
        const current = active;
        active = null;
        current.reject(new Error("Native request broker is disposed"));
      }
      rejectQueued(new Error("Native request broker is disposed"));
      closePort();
    },
  };
}
