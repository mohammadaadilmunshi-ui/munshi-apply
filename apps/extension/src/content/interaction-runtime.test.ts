// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { applyFillInstructions } from "./fill";
import { applyNavigationAction } from "./navigation";
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

describe("verified interaction runtime", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("fills an exact native multi-select set and rolls back an unsupported request", async () => {
    document.body.innerHTML = `
      <label for="skills">Skills</label>
      <select id="skills" multiple>
        <option value="excel">Excel</option>
        <option value="python">Python</option>
      </select>
    `;
    const question = scanDocument().questions[0]!;
    const select = document.getElementById("skills") as HTMLSelectElement;

    const first = await applyFillInstructions([
      {
        controlId: question.controlId,
        frameId: 0,
        value: '["Excel","Python"]',
        sensitive: false,
        approved: true,
      },
    ]);
    expect(first[0]?.status).toBe("FILLED");
    expect(
      Array.from(select.selectedOptions).map((option) => option.text),
    ).toEqual(["Excel", "Python"]);

    const second = await applyFillInstructions([
      {
        controlId: question.controlId,
        frameId: 0,
        value: '["Excel","Rust"]',
        sensitive: false,
        approved: true,
      },
    ]);
    expect(second[0]?.status).toBe("FAILED");
    expect(
      Array.from(select.selectedOptions).map((option) => option.text),
    ).toEqual(["Excel", "Python"]);
  });

  it("refuses final submission and allows only recognized forward navigation", () => {
    document.body.innerHTML = `<button id="final">Review and submit</button>`;
    const final = document.getElementById("final") as HTMLButtonElement;
    const finalClick = vi.fn();
    final.addEventListener("click", finalClick);
    const finalCandidate = scanDocument().navigationCandidates[0]!;
    expect(finalCandidate.action).toBe("FINAL_SUBMIT");
    expect(applyNavigationAction(finalCandidate.controlId).status).toBe(
      "REFUSED",
    );
    expect(finalClick).not.toHaveBeenCalled();

    document.body.innerHTML = `<button id="next">Continue</button>`;
    const next = document.getElementById("next") as HTMLButtonElement;
    const nextClick = vi.fn();
    next.addEventListener("click", nextClick);
    const nextCandidate = scanDocument().navigationCandidates[0]!;
    expect(nextCandidate.action).toBe("NEXT");
    expect(applyNavigationAction(nextCandidate.controlId).status).toBe(
      "NAVIGATED",
    );
    expect(nextClick).toHaveBeenCalledTimes(1);
  });
});
