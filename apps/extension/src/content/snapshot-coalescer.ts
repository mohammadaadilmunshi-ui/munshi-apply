export const SNAPSHOT_COALESCE_COOLDOWN_MS = 500;

export type SnapshotCoalescer = {
  request(force: boolean): Promise<void>;
  dispose(): void;
  pending(): boolean;
};

export function createSnapshotCoalescer(
  run: (force: boolean) => Promise<void>,
  cooldownMs = SNAPSHOT_COALESCE_COOLDOWN_MS,
): SnapshotCoalescer {
  let disposed = false;
  let running = false;
  let requested = false;
  let forceRequested = false;
  let current: Promise<void> = Promise.resolve();

  const cooldown = Math.max(0, cooldownMs);

  const drain = async (): Promise<void> => {
    while (!disposed && requested) {
      const force = forceRequested;
      requested = false;
      forceRequested = false;
      try {
        await run(force);
      } catch (error) {
        requested = false;
        forceRequested = false;
        throw error;
      }
      if (!disposed && requested && cooldown > 0) {
        await new Promise<void>((resolve) => setTimeout(resolve, cooldown));
      }
    }
  };

  return {
    request(force) {
      if (disposed) return Promise.resolve();
      requested = true;
      forceRequested ||= force;
      if (running) return current;

      running = true;
      current = drain().finally(() => {
        running = false;
      });
      return current;
    },
    dispose() {
      disposed = true;
      requested = false;
      forceRequested = false;
    },
    pending() {
      return running || requested;
    },
  };
}
