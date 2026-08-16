// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { scanDocument } from "./scanner";
import {
  beginTeachInteraction,
  cancelTeachInteraction,
  finishTeachInteraction,
} from "./teach";

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

describe("Teach MUNSHI capture", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("captures a demonstration as value-free reusable actions", () => {
    document.body.innerHTML = `
      <label for="country">Country</label>
      <input id="country" role="combobox" aria-expanded="false" aria-controls="countries" />
      <div id="countries" role="listbox">
        <div role="option">United States</div>
      </div>
    `;
    const page = scanDocument();
    const control = page.controls.find((item) => item.label === "Country")!;
    const input = document.getElementById("country") as HTMLInputElement;
    const started = beginTeachInteraction("teach-1", control.controlId);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.reusable).toBe(true);
    expect(learned.actions.map((action) => action.type)).toContain(
      "SELECT_EXACT_OPTION",
    );
    expect(JSON.stringify(learned)).not.toContain("United States");
  });

  it("cancels without retaining a demonstration", () => {
    document.body.innerHTML = `<label for="name">Name</label><input id="name" />`;
    const control = scanDocument().controls[0]!;
    const started = beginTeachInteraction("teach-2", control.controlId);
    expect(cancelTeachInteraction(started.sessionId).cancelled).toBe(true);
    expect(() => finishTeachInteraction(started.sessionId)).toThrow(
      /no longer active/,
    );
  });
});
