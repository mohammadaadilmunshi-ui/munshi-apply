import { describe, expect, it } from "vitest";
import { createBoundedHintStore } from "./bounded-hint-store";

describe("bounded control hint store", () => {
  it("evicts the least recently used hint after reaching the hard limit", () => {
    const hints = createBoundedHintStore<number>(3);
    hints.set("a", 1);
    hints.set("b", 2);
    hints.set("c", 3);

    expect(hints.get("a")).toBe(1);
    hints.set("d", 4);

    expect(hints.get("b")).toBeUndefined();
    expect(hints.get("a")).toBe(1);
    expect(hints.get("c")).toBe(3);
    expect(hints.get("d")).toBe(4);
    expect(hints.size()).toBe(3);
  });

  it("refreshes an existing key instead of growing the store", () => {
    const hints = createBoundedHintStore<number>(2);
    hints.set("a", 1);
    hints.set("b", 2);
    hints.set("a", 3);
    hints.set("c", 4);

    expect(hints.get("a")).toBe(3);
    expect(hints.get("b")).toBeUndefined();
    expect(hints.get("c")).toBe(4);
    expect(hints.size()).toBe(2);
  });

  it("normalizes invalid limits to at least one retained hint", () => {
    const hints = createBoundedHintStore<number>(0);
    hints.set("first", 1);
    hints.set("second", 2);

    expect(hints.get("first")).toBeUndefined();
    expect(hints.get("second")).toBe(2);
    expect(hints.size()).toBe(1);
  });
});
