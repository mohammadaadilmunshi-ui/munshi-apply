type Sleep = (milliseconds: number) => Promise<void>;

type CachedResponse = {
  response: unknown;
  capturedAt: number;
};

function successfulResponse(value: unknown): boolean {
  return Boolean(
    value &&
      typeof value === "object" &&
      "ok" in value &&
      (value as { ok?: unknown }).ok === true,
  );
}

export class NativeHealthStabilizer {
  private cached: CachedResponse | null = null;

  constructor(
    private readonly clock: () => number = () => Date.now(),
    private readonly retryDelays: readonly number[] = [120, 320],
    private readonly cacheTtlMs = 30_000,
  ) {}

  async request(
    send: () => Promise<unknown>,
    sleep: Sleep = (milliseconds) =>
      new Promise((resolve) => window.setTimeout(resolve, milliseconds)),
  ): Promise<unknown> {
    let lastResponse: unknown;
    let lastError: unknown;

    for (let attempt = 0; attempt <= this.retryDelays.length; attempt += 1) {
      try {
        const response = await send();
        lastResponse = response;
        if (successfulResponse(response)) {
          this.cached = { response, capturedAt: this.clock() };
          return response;
        }
      } catch (error) {
        lastError = error;
      }
      const delay = this.retryDelays[attempt];
      if (delay !== undefined) await sleep(delay);
    }

    if (
      this.cached &&
      this.clock() - this.cached.capturedAt <= this.cacheTtlMs
    ) {
      return this.cached.response;
    }
    if (lastResponse !== undefined) return lastResponse;
    throw lastError instanceof Error
      ? lastError
      : new Error("Native companion health check failed");
  }
}
