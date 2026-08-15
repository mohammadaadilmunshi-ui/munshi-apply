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

describe("AutoPilot page-state scanner", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
    window.history.replaceState({}, "", "/apply");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
      visibleRectangle,
    );
  });

  it("captures multiple select and autocomplete metadata", () => {
    document.body.innerHTML = `
      <label for="skills">Skills</label>
      <select id="skills" multiple autocomplete="off">
        <option>Excel</option><option>Power BI</option>
      </select>
    `;
    expect(scanDocument().controls[0]).toMatchObject({
      kind: "SELECT",
      multiple: true,
      autocomplete: "off",
      options: ["Excel", "Power BI"],
    });
  });

  it("captures ARIA validation messages", () => {
    document.body.innerHTML = `
      <label for="email">Email</label>
      <input id="email" aria-invalid="true" aria-describedby="email-error">
      <div id="email-error">Enter a valid email</div>
    `;
    const result = scanDocument();
    expect(result.controls[0]).toMatchObject({
      invalid: true,
      validationMessage: "Enter a valid email",
    });
    expect(result.validationErrorCount).toBe(1);
  });

  it("detects OTP and authentication security checkpoints", () => {
    document.body.innerHTML = `
      <h1>Verify your account</h1>
      <label for="otp">One-time verification code</label>
      <input id="otp" autocomplete="one-time-code">
    `;
    const result = scanDocument();
    expect(result.securityCheckpoint).toBe("OTP");
    expect(result.applicationState).toBe("VERIFY_ACCOUNT");
  });

  it("classifies recognized next and review actions", () => {
    document.body.innerHTML = `
      <button type="button">Continue</button>
      <button type="button">Review application</button>
    `;
    const actions = scanDocument().navigationCandidates.map(
      (candidate) => candidate.action,
    );
    expect(actions).toEqual(["NEXT", "REVIEW"]);
  });

  it("does not treat an application-entry Apply Now control as final submission", () => {
    document.body.innerHTML = `
      <button type="button">Apply Now</button>
      <button type="button">Next</button>
    `;
    const result = scanDocument();
    expect(
      result.navigationCandidates.map((candidate) => candidate.action),
    ).toEqual(["NEXT"]);
    expect(result.finalSubmissionBoundary).toBe(false);
  });

  it("treats Review and submit as a final manual boundary", () => {
    document.body.innerHTML = `<button type="submit">Review and submit</button>`;
    const result = scanDocument();
    expect(result.navigationCandidates[0]?.action).toBe("FINAL_SUBMIT");
    expect(result.finalSubmissionBoundary).toBe(true);
  });
});
