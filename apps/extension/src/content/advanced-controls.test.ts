// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import {
  fillAriaMultiSelectControl,
  fillStrictTemporalInput,
} from "./advanced-controls";

const timing = {
  optionTimeoutMs: 100,
  pollIntervalMs: 5,
  verificationTimeoutMs: 100,
  stabilityQuietMs: 5,
  stabilityTimeoutMs: 50,
};

describe("strict temporal controls", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it.each([
    ["month", "2026-12"],
    ["time", "17:45"],
    ["datetime-local", "2026-12-17T17:45"],
    ["week", "2026-W51"],
  ])("fills canonical %s values exactly", (type, value) => {
    const input = document.createElement("input");
    input.type = type;
    document.body.append(input);
    expect(fillStrictTemporalInput(input, value)).toBe(true);
    expect(input.value).toBe(value);
  });

  it.each([
    ["month", "12/2026"],
    ["time", "5:45 PM"],
    ["datetime-local", "2026-12-17 17:45Z"],
    ["week", "week 51 2026"],
  ])("rejects non-canonical %s values without guessing", (type, value) => {
    const input = document.createElement("input");
    input.type = type;
    document.body.append(input);
    expect(fillStrictTemporalInput(input, value)).toBe(false);
    expect(input.value).toBe("");
  });
});

describe("ARIA multi-select", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <label for="skills">Skills</label>
      <button id="skills" aria-haspopup="listbox" aria-controls="skill-list" aria-expanded="false">Choose</button>
      <div id="skill-list" role="listbox" aria-multiselectable="true">
        <div role="option" data-value="Excel" aria-selected="false">Excel</div>
        <div role="option" data-value="Power BI" aria-selected="false">Power BI</div>
        <div role="option" data-value="Python" aria-selected="true">Python</div>
      </div>
    `;
    const button = document.getElementById("skills")!;
    button.addEventListener("click", () =>
      button.setAttribute("aria-expanded", "true"),
    );
    for (const option of Array.from(
      document.querySelectorAll<HTMLElement>("[role='option']"),
    )) {
      option.addEventListener("click", () => {
        option.setAttribute(
          "aria-selected",
          option.getAttribute("aria-selected") === "true" ? "false" : "true",
        );
      });
    }
  });

  it("sets the exact requested set and removes extra selections", async () => {
    const button = document.getElementById("skills") as HTMLElement;
    const result = await fillAriaMultiSelectControl(
      button,
      '["Excel","Power BI"]',
      timing,
    );
    expect(result).toBe(true);
    const selected = Array.from(
      document.querySelectorAll<HTMLElement>(
        "[role='option'][aria-selected='true']",
      ),
    ).map((item) => item.dataset.value);
    expect(selected).toEqual(["Excel", "Power BI"]);
  });

  it("fails closed when one requested option is ambiguous", async () => {
    const list = document.getElementById("skill-list")!;
    list.insertAdjacentHTML(
      "beforeend",
      '<div role="option" data-value="Excel" aria-selected="false">Excel</div>',
    );
    const before = Array.from(
      document.querySelectorAll<HTMLElement>("[role='option']"),
    ).map((item) => item.getAttribute("aria-selected"));
    const result = await fillAriaMultiSelectControl(
      document.getElementById("skills") as HTMLElement,
      "Excel",
      timing,
    );
    expect(result).toBe(false);
    const after = Array.from(
      document.querySelectorAll<HTMLElement>("[role='option']"),
    ).map((item) => item.getAttribute("aria-selected"));
    expect(after).toEqual(before);
  });
});
