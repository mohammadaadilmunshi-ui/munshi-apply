import { describe, expect, it, vi } from "vitest";
import { createSnapshotRetryController } from "./snapshot-retry";

describe("snapshot delivery retry", () => {
  it("retries with bounded backoff and resets after success", () => {
    vi.useFakeTimers();
    const retry = vi.fn();
    const controller = createSnapshotRetryController(undefined, [10, 20]);

    expect(controller.failed(retry)).toBe(true);
    expect(controller.attempts()).toBe(1);
    vi.advanceTimersByTime(10);
    expect(retry).toHaveBeenCalledTimes(1);

    expect(controller.failed(retry)).toBe(true);
    vi.advanceTimersByTime(20);
    expect(retry).toHaveBeenCalledTimes(2);
    expect(controller.failed(retry)).toBe(false);

    controller.succeeded();
    expect(controller.attempts()).toBe(0);
    expect(controller.failed(retry)).toBe(true);
    vi.useRealTimers();
  });

  it("does not schedule duplicate retries while one is already pending", () => {
    vi.useFakeTimers();
    const retry = vi.fn();
    const controller = createSnapshotRetryController(undefined, [25]);

    expect(controller.failed(retry)).toBe(true);
    expect(controller.failed(retry)).toBe(false);
    vi.advanceTimersByTime(25);
    expect(retry).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("cancels pending work permanently when the content runtime is disposed", () => {
    vi.useFakeTimers();
    const retry = vi.fn();
    const controller = createSnapshotRetryController(undefined, [25, 50]);

    expect(controller.failed(retry)).toBe(true);
    controller.dispose();
    vi.runAllTimers();
    expect(retry).not.toHaveBeenCalled();
    expect(controller.failed(retry)).toBe(false);
    vi.useRealTimers();
  });
});
