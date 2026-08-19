// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import { scanDocument } from "./scanner";

describe("scanner application page identity", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
  });

  it("changes page identity when an explicit job query changes", () => {
    window.history.replaceState({}, "", "/apply?job=123");
    const first = scanDocument();

    window.history.replaceState({}, "", "/apply?job=456");
    const second = scanDocument();

    expect(first.pageId).not.toBe(second.pageId);
    expect(first.documentId).not.toBe(second.documentId);
  });

  it("keeps page identity stable when only tracking parameters change", () => {
    window.history.replaceState({}, "", "/apply?job=123&utm_source=a");
    const first = scanDocument();

    window.history.replaceState({}, "", "/apply?job=123&utm_source=b");
    const second = scanDocument();

    expect(first.pageId).toBe(second.pageId);
    expect(first.documentId).toBe(second.documentId);
  });
});
