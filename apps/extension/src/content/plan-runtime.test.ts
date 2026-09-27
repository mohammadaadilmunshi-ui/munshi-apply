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

  it("hashes the selected option for a protected check-one checkbox group", async () => {
    document.body.innerHTML = `
      <main>
        <h2>Self Identify</h2>
        <fieldset>
          <legend>Voluntary Self-Identification of Disability</legend>
          <p>Please check one of the boxes below:</p>
          <label><input type="checkbox" name="disability-choice" value="yes" />
            Yes, I have a disability, or have had one in the past
          </label>
          <label><input type="checkbox" name="disability-choice" value="no" checked />
            No, I do not have a disability and have not had one in the past
          </label>
          <label><input type="checkbox" name="disability-choice" value="decline" />
            I do not want to answer
          </label>
        </fieldset>
      </main>
    `;

    const described = await describeForm();
    const protectedField = described.fields.find(
      (field) => field.sensitivity_class === "SELF_ID",
    );

    expect(protectedField).toBeDefined();
    expect(protectedField?.display_value).toBe("[protected value]");
    expect(protectedField?.satisfied).toBe(true);
    expect(protectedField?.value_digest).toMatch(/^[0-9a-f]{64}$/);
  });

});
