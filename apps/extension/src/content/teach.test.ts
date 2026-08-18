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
    input.value = "United States";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.reusable).toBe(true);
    expect(learned.actions.map((action) => action.type)).toContain(
      "SELECT_EXACT_OPTION",
    );
    expect(JSON.stringify(learned)).not.toContain("United States");
  });

  it("rebinds when an ATS replaces the taught control after selection", () => {
    document.body.innerHTML = `
      <label for="ethnicity">Are you Hispanic/Latino?</label>
      <select id="ethnicity">
        <option value="">Select</option>
        <option value="no">No</option>
      </select>
    `;
    const initialPage = scanDocument();
    const control = initialPage.controls.find(
      (item) => item.label === "Are you Hispanic/Latino?",
    )!;
    const started = beginTeachInteraction("teach-dynamic", control.controlId);

    const original = document.getElementById("ethnicity") as HTMLSelectElement;
    const replacement = original.cloneNode(true) as HTMLSelectElement;
    replacement.value = "no";
    original.replaceWith(replacement);
    replacement.dispatchEvent(new Event("change", { bubbles: true }));

    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.reusable).toBe(true);
    expect(learned.quality.reasons).toContain("value-commit-observed");
    expect(learned.resolvedControlId).toBeTruthy();
    expect(JSON.stringify(learned)).not.toContain('"no"');
  });

  it("captures radio-group label clicks inside the taught field group", () => {
    document.body.innerHTML = `
      <fieldset>
        <legend>Race</legend>
        <label><input type="radio" name="race" value="a" /> Asian</label>
        <label><input type="radio" name="race" value="b" /> Other</label>
      </fieldset>
    `;
    const page = scanDocument();
    const control = page.controls.find(
      (item) => item.kind === "RADIO" && item.name === "race",
    )!;
    const started = beginTeachInteraction("teach-radio", control.controlId);
    const radios = Array.from(
      document.querySelectorAll<HTMLInputElement>('input[name="race"]'),
    );
    radios[1]!.checked = true;
    radios[1]!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    radios[1]!.dispatchEvent(new Event("change", { bubbles: true }));
    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.eventSequence.length).toBeGreaterThan(0);
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
