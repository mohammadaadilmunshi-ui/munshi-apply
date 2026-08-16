import { afterEach, describe, expect, it, vi } from "vitest";
import {
  disposePreviousContentRuntime,
  registerContentRuntime,
} from "./runtime-lifecycle";

afterEach(() => {
  disposePreviousContentRuntime();
});

describe("content runtime lifecycle", () => {
  it("disposes the previous runtime before registering a replacement", () => {
    const first = vi.fn();
    const second = vi.fn();

    registerContentRuntime(first);
    registerContentRuntime(second);

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();

    disposePreviousContentRuntime();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("makes runtime disposal idempotent", () => {
    const dispose = vi.fn();
    const release = registerContentRuntime(dispose);

    release();
    release();
    disposePreviousContentRuntime();

    expect(dispose).toHaveBeenCalledTimes(1);
  });

  it("allows a fresh runtime after an invalidated cleanup throws", () => {
    registerContentRuntime(() => {
      throw new Error("Extension context invalidated");
    });

    expect(() => disposePreviousContentRuntime()).not.toThrow();

    const next = vi.fn();
    registerContentRuntime(next);
    disposePreviousContentRuntime();
    expect(next).toHaveBeenCalledTimes(1);
  });
});
