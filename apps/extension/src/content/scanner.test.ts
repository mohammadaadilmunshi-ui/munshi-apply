// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
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

describe("universal page scanner", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("extracts native labels and semantic questions", () => {
    document.body.innerHTML = `
      <form>
        <label for="candidate-email">Email address</label>
        <input id="candidate-email" name="email" type="email" required>
      </form>
    `;

    const result = scanDocument();
    expect(result.controls).toHaveLength(1);
    expect(result.controls[0]).toMatchObject({
      kind: "EMAIL",
      label: "Email address",
      required: true,
    });
    expect(result.questions[0]).toMatchObject({
      semanticType: "EMAIL",
      requiresReview: false,
    });
  });

  it("excludes password and hidden controls from the application model", () => {
    document.body.innerHTML = `
      <input aria-label="Password" type="password">
      <input aria-label="Trap" style="display: none" type="text">
      <input aria-label="Phone" type="tel">
    `;

    const result = scanDocument();
    expect(result.controls).toHaveLength(1);
    expect(result.controls[0]?.kind).toBe("TEL");
  });

  it("includes legitimate controls below the current viewport", () => {
    document.body.innerHTML = `<input aria-label="LinkedIn" type="text">`;
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      ...visibleRectangle,
      bottom: 5030,
      top: 5000,
      y: 5000,
    });

    expect(scanDocument().questions[0]?.semanticType).toBe("LINKEDIN");
  });

  it("flags consequential sponsorship questions for review", () => {
    document.body.innerHTML = `
      <label for="sponsor">Will you now or in the future require sponsorship?</label>
      <select id="sponsor"><option>Choose</option><option>Yes</option><option>No</option></select>
    `;

    expect(scanDocument().questions[0]).toMatchObject({
      semanticType: "SPONSORSHIP_FUTURE",
      sensitive: true,
      requiresReview: true,
    });
  });

  it("discovers controls inside open shadow roots", () => {
    const host = document.createElement("job-application");
    document.body.append(host);
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <label for="portfolio">Portfolio URL</label>
      <input id="portfolio" type="url">
    `;

    expect(scanDocument().questions[0]).toMatchObject({
      rawText: "Portfolio URL",
      semanticType: "PORTFOLIO",
    });
  });
});
