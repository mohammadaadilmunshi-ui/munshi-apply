import { describe, expect, it, vi } from "vitest";
import { createSnapshotCoalescer } from "./snapshot-coalescer";

function deferred(): {
  promise: Promise<void>;
  resolve: () => void;
  reject: (error: Error) => void;
} {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("snapshot coalescer", () => {
  it("collapses a burst while one scan is running into one latest-state rerun", async () => {
    const first = deferred();
    const calls: boolean[] = [];
    const run = vi.fn(async (force: boolean) => {
      calls.push(force);
      if (calls.length === 1) await first.promise;
    });
    const coalescer = createSnapshotCoalescer(run);

    const active = coalescer.request(false);
    for (let index = 0; index < 100; index += 1) {
      void coalescer.request(false);
    }
    first.resolve();
    await active;

    expect(calls).toEqual([false, false]);
    expect(run).toHaveBeenCalledTimes(2);
    expect(coalescer.pending()).toBe(false);
  });

  it("upgrades the single queued rerun when any caller requires a forced scan", async () => {
    const first = deferred();
    const calls: boolean[] = [];
    const coalescer = createSnapshotCoalescer(async (force) => {
      calls.push(force);
      if (calls.length === 1) await first.promise;
    });

    const active = coalescer.request(false);
    void coalescer.request(false);
    void coalescer.request(true);
    void coalescer.request(false);
    first.resolve();
    await active;

    expect(calls).toEqual([false, true]);
  });

  it("clears failed backlog and permits a later recovery request", async () => {
    let attempts = 0;
    const coalescer = createSnapshotCoalescer(async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("background unavailable");
    });

    await expect(coalescer.request(false)).rejects.toThrow(
      "background unavailable",
    );
    expect(coalescer.pending()).toBe(false);
    await expect(coalescer.request(true)).resolves.toBeUndefined();
    expect(attempts).toBe(2);
  });

  it("suppresses all new work after disposal", async () => {
    const run = vi.fn(async () => undefined);
    const coalescer = createSnapshotCoalescer(run);
    coalescer.dispose();

    await coalescer.request(true);
    expect(run).not.toHaveBeenCalled();
    expect(coalescer.pending()).toBe(false);
  });
});
