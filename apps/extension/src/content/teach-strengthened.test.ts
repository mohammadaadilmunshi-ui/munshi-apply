// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  beginTeachInteraction,
  cancelTeachInteraction,
  finishTeachInteraction,
} from "./teach";
import { scanDocument } from "./scanner";

function installHtml(): string {
  document.body.innerHTML = `
    <label for="industry">Industry</label>
    <input id="industry" role="combobox" aria-controls="industry-list" />
    <ul id="industry-list" role="listbox"><li role="option">Automotive</li></ul>
    <button id="unrelated">Unrelated</button>
  `;
  const page = scanDocument();
  const control = page.controls.find((item) => item.label.includes("Industry"));
  if (!control) throw new Error("fixture control not found");
  return control.controlId;
}

beforeEach(() => {
  window.history.replaceState({}, "", "/apply");
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    bottom: 40,
    height: 30,
    left: 10,
    right: 210,
    top: 10,
    width: 200,
    x: 10,
    y: 10,
    toJSON: () => ({}),
  });
});

afterEach(() => {
  cancelTeachInteraction("cleanup-session");
  document.body.innerHTML = "";
});

describe("strengthened Teach MUNSHI capture", () => {
  it("does not promote unrelated page clicking into a reusable recipe", () => {
    const controlId = installHtml();
    beginTeachInteraction("teach-one-0001", controlId);
    document.querySelector<HTMLButtonElement>("#unrelated")!.click();
    const capture = finishTeachInteraction("teach-one-0001");
    expect(capture.changed).toBe(false);
    expect(capture.reusable).toBe(false);
    expect(capture.quality.score).toBeLessThan(0.8);
  });

  it("captures committed before and after state for the selected control", () => {
    const controlId = installHtml();
    beginTeachInteraction("teach-two-0002", controlId);
    const input = document.querySelector<HTMLInputElement>("#industry")!;
    input.value = "Automotive";
    input.dispatchEvent(new InputEvent("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const capture = finishTeachInteraction("teach-two-0002");
    expect(capture.changed).toBe(true);
    expect(capture.quality.valueCommitted).toBe(true);
    expect(capture.beforeState.valueLength).not.toBe(
      capture.afterState.valueLength,
    );
    expect(JSON.stringify(capture)).not.toContain("Automotive");
    expect(capture.quality.score).toBeGreaterThanOrEqual(0.8);
  });
});
