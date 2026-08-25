// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { scanDocument } from "./scanner";
import {
  focusControlForOwner,
  readControlValueForTeach,
} from "./field-navigation";

const visibleRectangle: DOMRect = {
  bottom: 40,
  height: 30,
  left: 10,
  right: 210,
  top: 10,
  width: 200,
  x: 10,
  y: 10,
  toJSON: () => ({}),
};

describe("owner field navigation", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <label for="phone">Mobile number</label>
      <input id="phone" name="phone" type="tel" value="555-0100">
    `;
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
    vi.spyOn(HTMLElement.prototype, "scrollIntoView").mockImplementation(
      () => undefined,
    );
  });

  it("scrolls, focuses and highlights a question without changing its value", () => {
    const page = scanDocument();
    const question = page.questions.find(
      (candidate) => candidate.semanticType === "PHONE",
    );
    expect(question).toBeDefined();
    const input = document.getElementById("phone") as HTMLInputElement;
    const before = input.value;

    const result = focusControlForOwner(question!.controlId);

    expect(result.status).toBe("FOCUSED");
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe(before);
    expect(input.hasAttribute("data-munshi-owner-focus")).toBe(true);
  });

  it("reads an owner-demonstrated value without storing it in a recipe", () => {
    const page = scanDocument();
    const question = page.questions.find(
      (candidate) => candidate.semanticType === "PHONE",
    );
    expect(question).toBeDefined();

    const result = readControlValueForTeach(question!.controlId);

    expect(result.status).toBe("READ");
    expect(result.value).toBe("555-0100");
  });

  it("fails closed when the employer control no longer exists", () => {
    const page = scanDocument();
    const question = page.questions[0]!;
    document.body.innerHTML = "<p>Field removed</p>";

    expect(focusControlForOwner(question.controlId).status).toBe("NOT_FOUND");
    expect(readControlValueForTeach(question.controlId).status).toBe(
      "NOT_FOUND",
    );
  });
});
