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
});
