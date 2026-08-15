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

  it("ignores passive reCAPTCHA integration until a challenge is active", () => {
    document.body.innerHTML = `
      <label for="resume">Upload CV</label>
      <input id="resume" type="file" required>
      <div class="grecaptcha-badge">
        <iframe title="reCAPTCHA" src="https://www.google.com/recaptcha/api2/anchor"></iframe>
      </div>
    `;
    const result = scanDocument();
    expect(result.securityCheckpoint).toBeNull();
    expect(result.applicationState).toBe("RESUME");
  });

  it("ignores a large invisible reCAPTCHA badge and passive branding", () => {
    document.body.innerHTML = `
      <label for="resume">Upload CV</label>
      <input id="resume" type="file" required>
      <p>This site is protected by reCAPTCHA and the Google Privacy Policy applies.</p>
      <div class="grecaptcha-badge">
        <iframe title="reCAPTCHA" src="https://www.google.com/recaptcha/api2/anchor?size=invisible"></iframe>
      </div>
    `;
    const frame = document.querySelector("iframe") as HTMLIFrameElement;
    vi.spyOn(frame, "getBoundingClientRect").mockReturnValue({
      ...visibleRectangle,
      bottom: 90,
      height: 80,
      right: 310,
      width: 300,
    });
    const result = scanDocument();
    expect(result.securityCheckpoint).toBeNull();
    expect(result.applicationState).toBe("RESUME");
  });

  it("detects a visible CAPTCHA prompt even without a challenge iframe", () => {
    document.body.innerHTML = `<p>Please complete the CAPTCHA verification to continue.</p>`;
    expect(scanDocument().securityCheckpoint).toBe("CAPTCHA");
  });

  it("detects a visible active CAPTCHA challenge", () => {
    document.body.innerHTML = `
      <iframe title="recaptcha challenge" src="https://www.google.com/recaptcha/api2/bframe"></iframe>
    `;
    expect(scanDocument().securityCheckpoint).toBe("CAPTCHA");
  });

  it("ignores hidden final-submit controls when inferring the current step", () => {
    document.body.innerHTML = `
      <label for="resume">Upload CV</label>
      <input id="resume" type="file" required>
      <button type="submit" style="display:none">Submit application</button>
      <button type="button">Continue</button>
    `;
    const result = scanDocument();
    expect(result.finalSubmissionBoundary).toBe(false);
    expect(result.applicationState).toBe("RESUME");
    expect(result.navigationCandidates.map((item) => item.action)).toEqual([
      "NEXT",
    ]);
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
