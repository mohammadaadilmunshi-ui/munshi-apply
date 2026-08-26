// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { focusOwnerControl, ownerControlValue } from "./owner-reliability";
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

describe("owner field navigation", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <label for="email">Email address</label>
      <input id="email" type="email" value="candidate@example.com">
      <label for="country">Country</label>
      <select id="country">
        <option>Choose</option>
        <option selected value="US">United States</option>
      </select>
    `;
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("scrolls to and focuses a question control without changing its value", () => {
    const page = scanDocument();
    const email = page.questions.find(
      (question) => question.semanticType === "EMAIL",
    );
    expect(email).toBeDefined();

    const result = focusOwnerControl(email!.controlId);

    expect(result.status).toBe("FOCUSED");
    expect(document.activeElement).toBe(document.getElementById("email"));
    expect((document.getElementById("email") as HTMLInputElement).value).toBe(
      "candidate@example.com",
    );
  });

  it("reads the committed human-facing option for Teach MUNSHI promotion", () => {
    const select = document.getElementById("country");
    expect(select).toBeInstanceOf(HTMLSelectElement);
    expect(ownerControlValue(select!)).toBe("United States");
  });
});
