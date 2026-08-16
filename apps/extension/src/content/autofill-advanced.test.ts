// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { applyFillInstructions } from "./fill";
import { optionEquivalent, repeatMetadataFor } from "./adaptive";
import { scanDocument } from "./scanner";

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

const quick = {
  optionTimeoutMs: 100,
  pollIntervalMs: 5,
  verificationTimeoutMs: 100,
  stabilityQuietMs: 5,
  stabilityTimeoutMs: 50,
};

describe("advanced adaptive autofill", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("maps only deterministic contextual synonyms", () => {
    expect(optionEquivalent("New Jersey", "NJ", "State / Province")).toBe(true);
    expect(optionEquivalent("Master of Science", "M.S.", "Degree")).toBe(true);
    expect(optionEquivalent("United States", "USA", "Country")).toBe(true);
    expect(optionEquivalent("New Jersey", "New York", "State")).toBe(false);
    expect(optionEquivalent("Apple", "Application", "Company")).toBe(false);
  });

  it("uses semantic equivalence for a native select without fuzzy guessing", async () => {
    document.body.innerHTML = `
      <label for="state">State</label>
      <select id="state"><option value="">Choose</option><option value="new-jersey">New Jersey</option></select>
    `;
    const question = scanDocument().questions[0]!;
    const result = await applyFillInstructions(
      [
        {
          controlId: question.controlId,
          frameId: 0,
          value: "NJ",
          sensitive: false,
          approved: true,
        },
      ],
      quick,
    );
    expect(result[0]?.status).toBe("FILLED");
    expect((document.getElementById("state") as HTMLSelectElement).value).toBe(
      "new-jersey",
    );
  });

  it("handles an ARIA switch only for an explicit boolean answer", async () => {
    document.body.innerHTML = `<div role="switch" aria-label="Remote preference" aria-checked="false" tabindex="0"></div>`;
    const control = document.querySelector<HTMLElement>("[role='switch']")!;
    control.addEventListener("click", () => {
      control.setAttribute(
        "aria-checked",
        control.getAttribute("aria-checked") === "true" ? "false" : "true",
      );
    });
    const question = scanDocument().questions[0]!;
    const result = await applyFillInstructions(
      [
        {
          controlId: question.controlId,
          frameId: 0,
          value: "Yes",
          sensitive: false,
          approved: true,
        },
      ],
      quick,
    );
    expect(result[0]?.status).toBe("FILLED");
    expect(control.getAttribute("aria-checked")).toBe("true");
  });

  it("handles a custom ARIA radio group with one semantic exact match", async () => {
    document.body.innerHTML = `
      <div role="radiogroup" aria-label="State">
        <div id="nj" role="radio" aria-checked="false" data-value="New Jersey">New Jersey</div>
        <div id="ny" role="radio" aria-checked="false" data-value="New York">New York</div>
      </div>
    `;
    const radios = Array.from(
      document.querySelectorAll<HTMLElement>("[role='radio']"),
    );
    for (const radio of radios) {
      radio.addEventListener("click", () => {
        radios.forEach((item) => item.setAttribute("aria-checked", "false"));
        radio.setAttribute("aria-checked", "true");
      });
    }
    const radio = scanDocument().controls.find(
      (control) => control.kind === "RADIO",
    )!;
    const result = await applyFillInstructions(
      [
        {
          controlId: radio.controlId,
          frameId: 0,
          value: "NJ",
          sensitive: false,
          approved: true,
        },
      ],
      quick,
    );
    expect(result[0]?.status).toBe("FILLED");
    expect(document.getElementById("nj")?.getAttribute("aria-checked")).toBe(
      "true",
    );
  });

  it("self-heals a uniquely identifiable control after a React-style re-render", async () => {
    document.body.innerHTML = `<label for="old-email">Email</label><input id="old-email" type="email">`;
    const original = scanDocument().questions[0]!;
    document.body.innerHTML = `<label for="new-email">Email</label><input id="new-email" type="email">`;
    const result = await applyFillInstructions(
      [
        {
          controlId: original.controlId,
          frameId: 0,
          value: "candidate@example.com",
          sensitive: false,
          approved: true,
        },
      ],
      quick,
    );
    expect(result[0]?.status).toBe("FILLED");
    expect(result[0]?.rebound).toBe(true);
    expect(
      (document.getElementById("new-email") as HTMLInputElement).value,
    ).toBe("candidate@example.com");
  });

  it("refuses to truncate an answer that exceeds the employer limit", async () => {
    document.body.innerHTML = `<label for="summary">Summary</label><textarea id="summary" maxlength="5"></textarea>`;
    const question = scanDocument().questions[0]!;
    const result = await applyFillInstructions(
      [
        {
          controlId: question.controlId,
          frameId: 0,
          value: "123456",
          sensitive: false,
          approved: true,
        },
      ],
      quick,
    );
    expect(result[0]?.status).toBe("FAILED");
    expect(
      (document.getElementById("summary") as HTMLTextAreaElement).value,
    ).toBe("");
    expect(result[0]?.reason).toContain("5-character limit");
  });

  it("selects an exact canonical date in a custom calendar", async () => {
    document.body.innerHTML = `
      <label for="start">Start date</label>
      <input id="start" aria-haspopup="dialog">
      <div role="dialog"><button id="day" role="gridcell" data-date="2026-12-17">17</button></div>
    `;
    const input = document.getElementById("start") as HTMLInputElement;
    const day = document.getElementById("day") as HTMLButtonElement;
    day.addEventListener("click", () => {
      input.value = "2026-12-17";
      day.setAttribute("aria-selected", "true");
    });
    const question = scanDocument().questions[0]!;
    const result = await applyFillInstructions(
      [
        {
          controlId: question.controlId,
          frameId: 0,
          value: "2026-12-17",
          sensitive: false,
          approved: true,
        },
      ],
      quick,
    );
    expect(result[0]?.status).toBe("FILLED");
    expect(input.value).toBe("12/17/2026");
  });

  it("marks repeated indexed controls without auto-creating records", () => {
    const input = document.createElement("input");
    input.name = "employment[2].employer";
    const repeat = repeatMetadataFor(input);
    expect(repeat.index).toBe(2);
    expect(repeat.groupId).toContain("[#]");
  });
});
