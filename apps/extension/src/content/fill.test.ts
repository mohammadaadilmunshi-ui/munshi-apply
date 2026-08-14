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

describe("guarded field filling", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <label for="email">Email address</label>
      <input id="email" type="email">
      <label for="sponsor">Will you now or in the future require sponsorship?</label>
      <select id="sponsor"><option>Choose</option><option>Yes</option><option>No</option></select>
    `;
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("fills only explicitly approved instructions", () => {
    const page = scanDocument();
    const email = page.questions.find(
      (question) => question.semanticType === "EMAIL",
    );
    const sponsorship = page.questions.find(
      (question) => question.semanticType === "SPONSORSHIP_FUTURE",
    );
    expect(email).toBeDefined();
    expect(sponsorship).toBeDefined();

    const results = applyFillInstructions([
      {
        controlId: email!.controlId,
        frameId: 0,
        value: "candidate@example.com",
        sensitive: false,
        approved: true,
      },
      {
        controlId: sponsorship!.controlId,
        frameId: 0,
        value: "Yes",
        sensitive: true,
        approved: false,
      },
    ]);

    expect((document.getElementById("email") as HTMLInputElement).value).toBe(
      "candidate@example.com",
    );
    expect(
      (document.getElementById("sponsor") as HTMLSelectElement).value,
    ).toBe("Choose");
    expect(results.map((result) => result.status)).toEqual([
      "FILLED",
      "SKIPPED",
    ]);
  });

  it("fills and verifies a control inside an open shadow root", () => {
    document.body.innerHTML = "";
    const host = document.createElement("candidate-profile");
    document.body.append(host);
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<input aria-label="Phone" type="tel">`;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = applyFillInstructions([
      {
        controlId: question!.controlId,
        frameId: 0,
        value: "+1 555 0100",
        sensitive: false,
        approved: true,
      },
    ]);

    expect((root.querySelector("input") as HTMLInputElement).value).toBe(
      "+1 555 0100",
    );
    expect(result[0]?.status).toBe("FILLED");
  });

  it("selects the requested option in a radio group", () => {
    document.body.innerHTML = `
      <fieldset>
        <legend>Will you now or in the future require sponsorship?</legend>
        <label><input type="radio" name="sponsor" value="Yes"> Yes</label>
        <label><input type="radio" name="sponsor" value="No"> No</label>
      </fieldset>
    `;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = applyFillInstructions([
      {
        controlId: question!.controlId,
        frameId: 0,
        value: "No",
        sensitive: true,
        approved: true,
      },
    ]);

    const radios = Array.from(
      document.querySelectorAll<HTMLInputElement>("input[type='radio']"),
    );
    expect(radios[0]?.checked).toBe(false);
    expect(radios[1]?.checked).toBe(true);
    expect(result[0]?.status).toBe("FILLED");
  });

  it("fills a checkbox only for an explicit boolean answer", () => {
    document.body.innerHTML = `
      <label><input id="agree" type="checkbox" checked> I agree</label>
    `;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = applyFillInstructions([
      {
        controlId: question!.controlId,
        frameId: 0,
        value: "No",
        sensitive: false,
        approved: true,
      },
    ]);

    expect((document.getElementById("agree") as HTMLInputElement).checked).toBe(
      false,
    );
    expect(result[0]?.status).toBe("FILLED");
  });

  it("does not mutate a checkbox for an ambiguous value", () => {
    document.body.innerHTML = `
      <label><input id="agree" type="checkbox" checked> I agree</label>
    `;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = applyFillInstructions([
      {
        controlId: question!.controlId,
        frameId: 0,
        value: "I agree",
        sensitive: false,
        approved: true,
      },
    ]);

    expect((document.getElementById("agree") as HTMLInputElement).checked).toBe(
      true,
    );
    expect(result[0]?.status).toBe("FAILED");
  });

  it("selects and verifies an exact option in an ARIA combobox", () => {
    document.body.innerHTML = `
      <label for="country">Country</label>
      <input id="country" role="combobox" aria-controls="country-options" value="">
      <div id="country-options" role="listbox">
        <div id="country-us" role="option">United States</div>
        <div id="country-ca" role="option">Canada</div>
      </div>
    `;
    const input = document.getElementById("country") as HTMLInputElement;
    const option = document.getElementById("country-us") as HTMLElement;
    option.addEventListener("click", () => {
      input.value = "United States";
      option.setAttribute("aria-selected", "true");
    });
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = applyFillInstructions([
      {
        controlId: question!.controlId,
        frameId: 0,
        value: "United States",
        sensitive: false,
        approved: true,
      },
    ]);

    expect(input.value).toBe("United States");
    expect(option.getAttribute("aria-selected")).toBe("true");
    expect(result[0]?.status).toBe("FILLED");
  });

  it("restores an ARIA combobox when no exact option can be verified", () => {
    document.body.innerHTML = `
      <label for="country">Country</label>
      <input id="country" role="combobox" aria-controls="country-options" value="Canada">
      <div id="country-options" role="listbox">
        <div role="option">Canada</div>
      </div>
    `;
    const input = document.getElementById("country") as HTMLInputElement;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = applyFillInstructions([
      {
        controlId: question!.controlId,
        frameId: 0,
        value: "United States",
        sensitive: false,
        approved: true,
      },
    ]);

    expect(input.value).toBe("Canada");
    expect(result[0]?.status).toBe("FAILED");
  });
});
