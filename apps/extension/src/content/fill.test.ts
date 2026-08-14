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

  it("fills only explicitly approved instructions", async () => {
    const page = scanDocument();
    const email = page.questions.find(
      (question) => question.semanticType === "EMAIL",
    );
    const sponsorship = page.questions.find(
      (question) => question.semanticType === "SPONSORSHIP_FUTURE",
    );
    expect(email).toBeDefined();
    expect(sponsorship).toBeDefined();

    const results = await applyFillInstructions([
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

  it("fills and verifies a control inside an open shadow root", async () => {
    document.body.innerHTML = "";
    const host = document.createElement("candidate-profile");
    document.body.append(host);
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<input aria-label="Phone" type="tel">`;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = await applyFillInstructions([
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

  it("selects the requested option in a radio group", async () => {
    document.body.innerHTML = `
      <fieldset>
        <legend>Will you now or in the future require sponsorship?</legend>
        <label><input type="radio" name="sponsor" value="Yes"> Yes</label>
        <label><input type="radio" name="sponsor" value="No"> No</label>
      </fieldset>
    `;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = await applyFillInstructions([
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

  it("fills a checkbox only for an explicit boolean answer", async () => {
    document.body.innerHTML = `
      <label><input id="agree" type="checkbox" checked> I agree</label>
    `;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = await applyFillInstructions([
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

  it("does not mutate a checkbox for an ambiguous value", async () => {
    document.body.innerHTML = `
      <label><input id="agree" type="checkbox" checked> I agree</label>
    `;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = await applyFillInstructions([
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

  it("selects and verifies an exact option in an ARIA combobox", async () => {
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

    const result = await applyFillInstructions(
      [
        {
          controlId: question!.controlId,
          frameId: 0,
          value: "United States",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );

    expect(input.value).toBe("United States");
    expect(option.getAttribute("aria-selected")).toBe("true");
    expect(result[0]?.status).toBe("FILLED");
  });

  it("waits for an exact async autocomplete option before selecting", async () => {
    document.body.innerHTML = `
      <label for="city">City</label>
      <input id="city" role="combobox" aria-controls="city-options" value="">
      <div id="city-options" role="listbox"></div>
    `;
    const input = document.getElementById("city") as HTMLInputElement;
    const container = document.getElementById("city-options") as HTMLElement;
    input.addEventListener(
      "input",
      () => {
        setTimeout(() => {
          const option = document.createElement("div");
          option.id = "city-phl";
          option.setAttribute("role", "option");
          option.textContent = "Philadelphia";
          option.addEventListener("click", () => {
            input.value = "Philadelphia";
            option.setAttribute("aria-selected", "true");
          });
          container.append(option);
        }, 10);
      },
      { once: true },
    );
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = await applyFillInstructions(
      [
        {
          controlId: question!.controlId,
          frameId: 0,
          value: "Philadelphia",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );

    expect(input.value).toBe("Philadelphia");
    expect(result[0]?.status).toBe("FILLED");
  });

  it("supports one exact portaled option without fuzzy matching", async () => {
    document.body.innerHTML = `
      <label for="state">State</label>
      <input id="state" role="combobox" value="">
      <div id="portal-root">
        <div id="state-nj" role="option">New Jersey</div>
      </div>
    `;
    const input = document.getElementById("state") as HTMLInputElement;
    const option = document.getElementById("state-nj") as HTMLElement;
    option.addEventListener("click", () => {
      input.value = "New Jersey";
      option.setAttribute("aria-selected", "true");
    });
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = await applyFillInstructions(
      [
        {
          controlId: question!.controlId,
          frameId: 0,
          value: "New Jersey",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );

    expect(input.value).toBe("New Jersey");
    expect(result[0]?.status).toBe("FILLED");
  });

  it("fails closed when multiple portaled options have the same exact value", async () => {
    document.body.innerHTML = `
      <label for="country">Country</label>
      <input id="country" role="combobox" value="Canada">
      <div role="option">United States</div>
      <div role="option">United States</div>
    `;
    const input = document.getElementById("country") as HTMLInputElement;
    const question = scanDocument().questions[0];
    expect(question).toBeDefined();

    const result = await applyFillInstructions(
      [
        {
          controlId: question!.controlId,
          frameId: 0,
          value: "United States",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );

    expect(input.value).toBe("Canada");
    expect(result[0]?.status).toBe("FAILED");
  });

  it("restores an ARIA combobox when no exact option can be verified", async () => {
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

    const result = await applyFillInstructions(
      [
        {
          controlId: question!.controlId,
          frameId: 0,
          value: "United States",
          sensitive: false,
          approved: true,
        },
      ],
      quickInteraction,
    );

    expect(input.value).toBe("Canada");
    expect(result[0]?.status).toBe("FAILED");
  });

  it("fills only a canonical valid native date and verifies it exactly", async () => {
    document.body.innerHTML = `
      <label for="start-date">Start date</label>
      <input id="start-date" type="date">
    `;
    const input = document.getElementById("start-date") as HTMLInputElement;
    const control = scanDocument().controls.find(
      (candidate) => candidate.kind === "DATE",
    );
    expect(control).toBeDefined();

    const valid = await applyFillInstructions([
      {
        controlId: control!.controlId,
        frameId: 0,
        value: "2026-12-17",
        sensitive: false,
        approved: true,
      },
    ]);
    expect(valid[0]?.status).toBe("FILLED");
    expect(input.value).toBe("2026-12-17");

    const invalid = await applyFillInstructions([
      {
        controlId: control!.controlId,
        frameId: 0,
        value: "12/17/2026",
        sensitive: false,
        approved: true,
      },
    ]);
    expect(invalid[0]?.status).toBe("FAILED");
    expect(input.value).toBe("2026-12-17");
  });
});
