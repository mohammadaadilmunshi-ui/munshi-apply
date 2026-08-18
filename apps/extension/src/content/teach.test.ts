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

  it("rebinds by stable label when a dynamic ATS changes the control fingerprint", () => {
    document.body.innerHTML = `
        <label for="race">Please identify your race</label>
        <input id="race" role="combobox" aria-expanded="false" aria-haspopup="listbox" />
      `;
    const initialPage = scanDocument();
    const control = initialPage.controls.find(
      (item) => item.label === "Please identify your race",
    )!;
    const started = beginTeachInteraction(
      "teach-label-rebind",
      control.controlId,
    );

    const original = document.getElementById("race") as HTMLInputElement;
    const replacement = document.createElement("select");
    replacement.id = "race";
    replacement.innerHTML = `
        <option value="">Select</option>
        <option value="asian">Asian</option>
      `;
    replacement.value = "asian";
    original.replaceWith(replacement);
    replacement.dispatchEvent(new Event("change", { bubbles: true }));

    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.reusable).toBe(true);
    expect(learned.quality.reasons).toContain("dynamic-control-rebound");
    expect(JSON.stringify(learned)).not.toContain("Asian");
  });

  it("accepts a same-value demonstration when an explicit commit event proves the mechanics", () => {
    document.body.innerHTML = `
        <label for="ethnicity">Are you Hispanic/Latino?</label>
        <select id="ethnicity">
          <option value="">Select</option>
          <option value="no" selected>No</option>
        </select>
      `;
    const page = scanDocument();
    const control = page.controls.find(
      (item) => item.label === "Are you Hispanic/Latino?",
    )!;
    const select = document.getElementById("ethnicity") as HTMLSelectElement;
    const started = beginTeachInteraction(
      "teach-same-value",
      control.controlId,
    );

    select.dispatchEvent(new Event("change", { bubbles: true }));

    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.changed).toBe(false);
    expect(learned.reusable).toBe(true);
    expect(learned.quality.reasons).toContain("same-value-demonstration");
    expect(learned.quality.reasons).toContain("explicit-commit-observed");
  });

  it("accepts a portaled custom-select option click without retaining the answer", () => {
    document.body.innerHTML = `
        <div id="race-shell">
          <label for="race">Please identify your race</label>
          <input id="race" role="combobox" aria-expanded="false" aria-haspopup="listbox" />
          <span id="visible-choice">Select</span>
        </div>
        <div id="portal" role="listbox">
          <div id="asian-option" role="option">Asian</div>
        </div>
      `;
    const page = scanDocument();
    const control = page.controls.find(
      (item) => item.label === "Please identify your race",
    )!;
    const input = document.getElementById("race") as HTMLInputElement;
    const option = document.getElementById("asian-option") as HTMLElement;
    const visibleChoice = document.getElementById("visible-choice")!;
    const started = beginTeachInteraction("teach-portal", control.controlId);

    input.setAttribute("aria-expanded", "true");
    input.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    visibleChoice.textContent = "Asian";
    input.setAttribute("aria-expanded", "false");
    option.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const learned = finishTeachInteraction(started.sessionId);
    expect(learned.reusable).toBe(true);
    expect(
      learned.eventSequence.some((event) => event.target === "owned-popup"),
    ).toBe(true);
    expect(learned.quality.reasons).toContain("explicit-commit-observed");
    expect(JSON.stringify(learned)).not.toContain("Asian");
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
