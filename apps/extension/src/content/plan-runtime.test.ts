// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { describeForm } from "./plan-runtime";

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

describe("plan runtime provider-backed evidence", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("does not treat typed Workday prompt query text as a committed answer", async () => {
    document.body.innerHTML = `
      <div data-automation-id="prompt">
        <label for="source">How did you hear about us? *</label>
        <input
          id="source"
          data-automation-id="promptInput"
          role="combobox"
          aria-haspopup="listbox"
          aria-autocomplete="list"
          value="Example Source"
          required
        />
      </div>
    `;

    const described = await describeForm();
    const field = described.fields.find(
      (candidate) => candidate.semantic_type === "REFERRAL",
    );

    expect(field).toBeDefined();
    expect(field?.display_value).toBe("");
    expect(field?.satisfied).toBe(false);
  });

  it("accepts the exact Workday selected item rather than the typed query", async () => {
    document.body.innerHTML = `
      <div data-automation-id="prompt">
        <label for="source">How did you hear about us? *</label>
        <input
          id="source"
          data-automation-id="promptInput"
          role="combobox"
          aria-haspopup="listbox"
          aria-autocomplete="list"
          value="uncommitted query text"
          required
        />
        <div data-automation-id="selectedItem">
          <span data-automation-id="promptOption">Example Source</span>
        </div>
      </div>
    `;

    const described = await describeForm();
    const field = described.fields.find(
      (candidate) => candidate.semantic_type === "REFERRAL",
    );

    expect(field).toBeDefined();
    expect(field?.display_value).toBe("Example Source");
    expect(field?.satisfied).toBe(true);
  });

  it("preserves protected, self-id, and post-offer sensitivity classes", async () => {
    document.body.innerHTML = `
      <label for="age">Are you at least 18 years of age? *</label>
      <select id="age" required><option>Yes</option></select>

      <label for="gender">What is your gender? *</label>
      <select id="gender" required><option>Example choice</option></select>

      <label for="employee-id">Employee ID (if applicable)</label>
      <input id="employee-id" />
    `;

    const described = await describeForm();
    const bySemantic = new Map(
      described.fields.map((field) => [field.semantic_type, field]),
    );

    expect(bySemantic.get("AGE_18_PLUS")?.sensitivity_class).toBe("PROTECTED");
    expect(bySemantic.get("GENDER")?.sensitivity_class).toBe("SELF_ID");
    expect(bySemantic.get("EMPLOYEE_ID")?.sensitivity_class).toBe("POST_OFFER");
    expect(bySemantic.get("GENDER")?.display_value).toBe("[protected value]");
  });
});
