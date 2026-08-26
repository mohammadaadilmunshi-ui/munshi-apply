// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { applyFillInstructions } from "./fill";
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

const quickInteraction = {
  optionTimeoutMs: 80,
  pollIntervalMs: 5,
  verificationTimeoutMs: 80,
};

function controlId(label: string): string {
  const page = scanDocument();
  const control = page.controls.find((candidate) => candidate.label === label);
  if (!control) throw new Error(`Missing control: ${label}`);
  return control.controlId;
}

describe("universal native application filling", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <h2>Basic Information</h2>
      <label for="state">State/Province</label>
      <select id="state">
        <option value="">Select an option</option>
        <option value="NJ_CODE">New Jersey</option>
        <option value="NY_CODE">New York</option>
      </select>

      <section>
        <h2>Education History</h2>
        <label for="degree">Highest level of education obtained or in progress</label>
        <select id="degree">
          <option value="">Select an option</option>
          <option value="bachelors">Bachelor's Degree</option>
          <option value="masters">Master's Degree</option>
        </select>

        <label for="field">Field of study</label>
        <select id="field">
          <option value="">Select an option</option>
          <option value="hr">Human Resources</option>
          <option value="analytics">Analytics</option>
        </select>

        <label for="education-start">Start Date</label>
        <input id="education-start" type="month">
      </section>

      <section>
        <h2>Work History</h2>
        <label for="employment-start">Start date</label>
        <input id="employment-start" type="month">

        <label for="industry">Company Industry</label>
        <select id="industry">
          <option value="">Select an option</option>
          <option value="automotive">Automotive &amp; Mobility</option>
          <option value="consulting">Consulting</option>
        </select>

        <label for="function">Position Function</label>
        <select id="function">
          <option value="">Select an option</option>
          <option value="human-capital">Human Capital</option>
          <option value="operations">Operations</option>
        </select>
      </section>
    `;
    document.title = "Bain application";
    window.history.replaceState({}, "", "/jobs/Register?folderId=108235");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("normalizes state abbreviations to full employer options", async () => {
    const results = await applyFillInstructions(
      [
        {
          controlId: controlId("State/Province"),
          frameId: 0,
          value: "NJ",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );
    expect(results[0]?.status).toBe("FILLED");
    expect((document.getElementById("state") as HTMLSelectElement).value).toBe(
      "NJ_CODE",
    );
  });

  it("maps specific degree evidence to a generic employer degree option", async () => {
    const results = await applyFillInstructions(
      [
        {
          controlId: controlId(
            "Highest level of education obtained or in progress",
          ),
          frameId: 0,
          value: "Master of Science",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );
    expect(results[0]?.status).toBe("FILLED");
    expect((document.getElementById("degree") as HTMLSelectElement).value).toBe(
      "masters",
    );
  });

  it("maps HR-focused interdisciplinary study to Human Resources", async () => {
    const results = await applyFillInstructions(
      [
        {
          controlId: controlId("Field of study"),
          frameId: 0,
          value: "Human Resource and Analytics",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );
    expect(results[0]?.status).toBe("FILLED");
    expect((document.getElementById("field") as HTMLSelectElement).value).toBe(
      "hr",
    );
  });

  it("coerces full profile dates into native month controls", async () => {
    const page = scanDocument();
    const start = page.questions.find(
      (candidate) => candidate.semanticType === "EMPLOYMENT_START_DATE",
    );
    expect(start).toBeDefined();
    const results = await applyFillInstructions(
      [
        {
          controlId: start!.controlId,
          frameId: 0,
          value: "2024-07-01",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );
    expect(results[0]?.status).toBe("FILLED");
    expect(
      (document.getElementById("employment-start") as HTMLInputElement).value,
    ).toBe("2024-07");
  });

  it("normalizes employer industry and position-function taxonomies", async () => {
    const results = await applyFillInstructions(
      [
        {
          controlId: controlId("Company Industry"),
          frameId: 0,
          value: "Automotive",
          sensitive: false,
          approved: true,
        },
        {
          controlId: controlId("Position Function"),
          frameId: 0,
          value: "Human Resources",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );
    expect(results.map((item) => item.status)).toEqual(["FILLED", "FILLED"]);
    expect(
      (document.getElementById("industry") as HTMLSelectElement).value,
    ).toBe("automotive");
    expect(
      (document.getElementById("function") as HTMLSelectElement).value,
    ).toBe("human-capital");
  });
});
