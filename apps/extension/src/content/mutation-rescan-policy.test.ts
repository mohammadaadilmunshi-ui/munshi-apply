// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import { shouldRescanFromMutations } from "./mutation-rescan-policy";

function attributeRecord(
  target: Element,
  attributeName: string,
): MutationRecord {
  return {
    type: "attributes",
    target,
    addedNodes: [] as unknown as NodeList,
    removedNodes: [] as unknown as NodeList,
    previousSibling: null,
    nextSibling: null,
    attributeName,
    attributeNamespace: null,
    oldValue: null,
  };
}

function childRecord(target: Element): MutationRecord {
  return {
    type: "childList",
    target,
    addedNodes: [] as unknown as NodeList,
    removedNodes: [] as unknown as NodeList,
    previousSibling: null,
    nextSibling: null,
    attributeName: null,
    attributeNamespace: null,
    oldValue: null,
  };
}

describe("mutation rescan policy", () => {
  it("ignores decorative class and style churn with no application controls", () => {
    const decoration = document.createElement("div");
    decoration.innerHTML = `<span class="spinner">Loading</span>`;
    expect(
      shouldRescanFromMutations([
        attributeRecord(decoration, "class"),
        attributeRecord(decoration.querySelector("span")!, "style"),
      ]),
    ).toBe(false);
  });

  it("rescans when class or style can affect a control subtree", () => {
    const section = document.createElement("section");
    section.innerHTML = `<label for="email">Email</label><input id="email">`;
    expect(shouldRescanFromMutations([attributeRecord(section, "class")])).toBe(
      true,
    );
  });

  it("always rescans structural child-list changes", () => {
    const root = document.createElement("div");
    expect(shouldRescanFromMutations([childRecord(root)])).toBe(true);
  });

  it("rescans semantic and validation attributes even on plain elements", () => {
    const node = document.createElement("div");
    expect(
      shouldRescanFromMutations([attributeRecord(node, "aria-hidden")]),
    ).toBe(true);
  });
});
