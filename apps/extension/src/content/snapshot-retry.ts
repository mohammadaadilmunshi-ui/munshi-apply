export const SNAPSHOT_RETRY_DELAYS_MS = [250, 1_000, 3_000] as const;

type TimerId = ReturnType<typeof setTimeout>;

type SnapshotRetryScheduler = {
  schedule(callback: () => void, delayMs: number): TimerId;
  cancel(timerId: TimerId): void;
};

const defaultScheduler: SnapshotRetryScheduler = {
  schedule: (callback, delayMs) => setTimeout(callback, delayMs),
  cancel: (timerId) => clearTimeout(timerId),
};

export type SnapshotRetryController = {
  failed(retry: () => void): boolean;
  succeeded(): void;
  dispose(): void;
  attempts(): number;
};

export function createSnapshotRetryController(
  scheduler: SnapshotRetryScheduler = defaultScheduler,
  delays: readonly number[] = SNAPSHOT_RETRY_DELAYS_MS,
): SnapshotRetryController {
  let attempt = 0;
  let timer: TimerId | null = null;
  let disposed = false;

  const cancelPending = (): void => {
    if (timer === null) return;
    scheduler.cancel(timer);
    timer = null;
  };

  return {
    failed(retry) {
      if (disposed || timer !== null || attempt >= delays.length) return false;
      const delay = Math.max(0, delays[attempt] ?? 0);
      attempt += 1;
      timer = scheduler.schedule(() => {
        timer = null;
        if (!disposed) retry();
      }, delay);
      return true;
    },
    succeeded() {
      attempt = 0;
      cancelPending();
    },
    dispose() {
      disposed = true;
      cancelPending();
    },
    attempts() {
      return attempt;
    },
  };
}
