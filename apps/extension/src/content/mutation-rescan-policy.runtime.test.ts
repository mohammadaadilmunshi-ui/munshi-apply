// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import { shouldRescanFromMutations } from "./mutation-rescan-policy";

describe("production mutation rescan policy", () => {
  it("ignores text-only ATS status churn", () => {
    const host = document.createElement("div");
    const status = document.createTextNode("Analyzing resume...Success!");
    const record = {
      type: "childList",
      target: host,
      addedNodes: [status],
      removedNodes: [],
    } as unknown as MutationRecord;
    expect(shouldRescanFromMutations([record])).toBe(false);
  });

  it("rescans when a new application control is inserted", () => {
    const host = document.createElement("div");
    const input = document.createElement("input");
    const record = {
      type: "childList",
      target: host,
      addedNodes: [input],
      removedNodes: [],
    } as unknown as MutationRecord;
    expect(shouldRescanFromMutations([record])).toBe(true);
  });
});
