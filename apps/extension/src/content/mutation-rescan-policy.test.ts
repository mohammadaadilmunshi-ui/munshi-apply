// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import {
  isApplicationRelevantTarget,
  shouldRescanFromMutations,
} from "./mutation-rescan-policy";

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

function childRecord(
  target: Element,
  addedNodes: Node[] = [],
  removedNodes: Node[] = [],
): MutationRecord {
  return {
    type: "childList",
    target,
    addedNodes: addedNodes as unknown as NodeList,
    removedNodes: removedNodes as unknown as NodeList,
    previousSibling: null,
    nextSibling: null,
    attributeName: null,
    attributeNamespace: null,
    oldValue: null,
  };
}

describe("mutation rescan policy", () => {
  it("ignores decorative class, style, and aria churn with no application controls", () => {
    const decoration = document.createElement("div");
    decoration.innerHTML = `<span class="spinner">Loading</span>`;
    expect(
      shouldRescanFromMutations([
        attributeRecord(decoration, "class"),
        attributeRecord(decoration.querySelector("span")!, "style"),
        attributeRecord(decoration, "aria-hidden"),
      ]),
    ).toBe(false);
  });

  it("rescans when attributes can affect a control subtree", () => {
    const section = document.createElement("section");
    section.innerHTML = `<label for="email">Email</label><input id="email">`;
    expect(shouldRescanFromMutations([attributeRecord(section, "class")])).toBe(
      true,
    );
    expect(
      shouldRescanFromMutations([attributeRecord(section, "aria-hidden")]),
    ).toBe(true);
  });

  it("ignores structural child-list records with no application controls", () => {
    const root = document.createElement("div");
    expect(shouldRescanFromMutations([childRecord(root)])).toBe(false);
    expect(
      shouldRescanFromMutations([
        childRecord(root, [document.createElement("span")]),
      ]),
    ).toBe(false);
  });

  it("rescans when application controls are inserted or removed", () => {
    const root = document.createElement("div");
    const input = document.createElement("input");
    expect(shouldRescanFromMutations([childRecord(root, [input])])).toBe(true);
    expect(shouldRescanFromMutations([childRecord(root, [], [input])])).toBe(
      true,
    );
  });

  it("recognizes interaction targets inside application controls and forms", () => {
    const form = document.createElement("form");
    form.innerHTML = `<button><span id="label">Continue</span></button>`;
    const label = form.querySelector("#label")!;
    expect(isApplicationRelevantTarget(label)).toBe(true);
    expect(isApplicationRelevantTarget(document.createElement("div"))).toBe(
      false,
    );
  });
});
