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

  it("maps SMS code prompts and passkey prompts into protected checkpoints", () => {
    document.body.innerHTML = `
      <p>We sent an SMS verification code to your mobile phone.</p>
      <input autocomplete="one-time-code">
    `;
    expect(scanDocument().securityCheckpoint).toBe("OTP");

    document.body.innerHTML = `
      <main>
        <h1>Sign in with your passkey</h1>
        <button type="button">Use security key</button>
      </main>
    `;
    expect(scanDocument().securityCheckpoint).toBe("AUTHENTICATION");
  });

  it("does not combine ordinary Workday phone and postal fields into an OTP checkpoint", () => {
    document.body.innerHTML = `
      <section aria-label="Phone">
        <label for="phone-type">Phone Device Type Mobile Required</label>
        <button id="phone-type" type="button">Mobile</button>
        <label for="phone-number">Phone Number*</label>
        <input id="phone-number" type="text">
      </section>
      <section aria-label="Address">
        <label for="postal-code">Postal Code</label>
        <input id="postal-code" type="text">
      </section>
    `;

    expect(scanDocument().securityCheckpoint).toBeNull();
  });

  it("observes segmented phone controls as four distinct semantic questions", () => {
    document.body.innerHTML = `
      <section aria-label="Phone">
        <label for="phone-type">Phone Device Type *</label>
        <select id="phone-type" name="phoneNumber--phoneType">
          <option>Select One</option><option>Mobile</option>
        </select>
        <label for="phone-code">Country Phone Code *</label>
        <div id="phone-code" role="combobox" aria-label="Country Phone Code"></div>
        <label for="phone-number">Phone Number *</label>
        <input id="phone-number" name="phoneNumber--phoneNumber" type="tel">
        <label for="phone-ext">Phone Extension</label>
        <input id="phone-ext" name="phoneNumber--extension" type="text">
      </section>
    `;

    const semantics = scanDocument().questions.map(
      (candidate) => candidate.semanticType,
    );
    expect(semantics).toContain("PHONE_DEVICE_TYPE");
    expect(semantics).toContain("PHONE_COUNTRY_CODE");
    expect(semantics).toContain("PHONE");
    expect(semantics).toContain("PHONE_EXTENSION");
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

  it("ignores anti-bot challenge frames hidden by an ancestor", () => {
    document.body.innerHTML = `
      <label for="first">First Name *</label>
      <input id="first" required>
      <div style="opacity: 0">
        <iframe title="recaptcha challenge" src="https://www.google.com/recaptcha/api2/bframe"></iframe>
      </div>
    `;
    const frame = document.querySelector("iframe") as HTMLIFrameElement;
    vi.spyOn(frame, "getBoundingClientRect").mockReturnValue({
      ...visibleRectangle,
      bottom: 500,
      height: 400,
      right: 500,
      width: 400,
    });
    expect(scanDocument().securityCheckpoint).toBeNull();
  });

  it("ignores an explicitly invisible CAPTCHA frame with challenge tokens", () => {
    document.body.innerHTML = `
      <label for="email">Email Address *</label>
      <input id="email" type="email" required>
      <iframe title="recaptcha challenge" src="https://www.google.com/recaptcha/api2/bframe?size=invisible"></iframe>
    `;
    const frame = document.querySelector("iframe") as HTMLIFrameElement;
    vi.spyOn(frame, "getBoundingClientRect").mockReturnValue({
      ...visibleRectangle,
      bottom: 500,
      height: 400,
      right: 500,
      width: 400,
    });
    expect(scanDocument().securityCheckpoint).toBeNull();
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

  it("recovers a nearby prompt for a custom select instead of its placeholder", () => {
    document.body.innerHTML = `
      <div class="question-field">
        <label>How did you hear about us? *</label>
        <div id="source" role="combobox" aria-haspopup="listbox" aria-label="-- Select one --"></div>
      </div>
    `;
    const question = scanDocument().questions[0];
    expect(question).toMatchObject({
      rawText: "How did you hear about us? *",
      semanticType: "REFERRAL",
    });
  });

  it("emits a value-free Universal Brain question observation", () => {
    document.body.innerHTML = `
      <section aria-label="Contact Address">
        <p>Residence details</p>
        <label for="state">State / Province *</label>
        <select id="state" name="candidate_region" autocomplete="address-level1" required>
          <option>New Jersey</option>
          <option>New York</option>
        </select>
        <label for="zip">Postal code</label>
        <input id="zip" name="postal" autocomplete="postal-code" />
      </section>
    `;
    const result = scanDocument();
    const question = result.questions.find(
      (candidate) => candidate.semanticType === "STATE_PROVINCE",
    );
    expect(question).toMatchObject({
      label: "State / Province *",
      sectionHeading: "Contact Address",
      fieldName: "candidate_region",
      elementId: "state",
      autocomplete: "address-level1",
      options: ["New Jersey", "New York"],
      semanticConfidence: expect.any(Number),
      optionSignature: expect.any(String),
      inputConstraints: expect.objectContaining({ required: true }),
      logicalFieldFingerprintInputs: expect.objectContaining({
        sectionHeading: "Contact Address",
        fieldName: "candidate_region",
        optionSignature: expect.any(String),
      }),
    });
    expect(JSON.stringify(question)).not.toContain("candidate answer");
  });

  it("keeps repeated employment rows semantically isolated despite identical labels", () => {
    document.body.innerHTML = `
      <section aria-label="Work history">
        <div class="employment-row">
          <label for="employer-0">Employer</label>
          <input id="employer-0" name="employment[0].employer" required />
        </div>
        <div class="employment-row">
          <label for="employer-1">Employer</label>
          <input id="employer-1" name="employment[1].employer" required />
        </div>
      </section>
    `;
    const employers = scanDocument().questions.filter(
      (candidate) => candidate.label === "Employer",
    );
    expect(employers).toHaveLength(2);
    expect(employers[0]?.repeatGroupId).toBe(employers[1]?.repeatGroupId);
    expect(employers[0]?.repeatGroupId).toContain("[#]");
    expect(employers.map((item) => item.repeatIndex)).toEqual([0, 1]);
    expect(
      employers.map((item) => item.logicalFieldFingerprintInputs?.repeatIndex),
    ).toEqual([0, 1]);
    expect(employers[0]?.controlId).not.toBe(employers[1]?.controlId);
  });

  it("discovers a focusable select shell without native or ARIA select semantics", () => {
    document.body.innerHTML = `
    <div class="application-field">
      <label>Years of Experience *</label>
      <div id="years" class="experience-select" tabindex="0">Select an option</div>
    </div>
  `;
    const result = scanDocument();
    expect(result.controls).toContainEqual(
      expect.objectContaining({
        kind: "COMBOBOX",
        label: "Years of Experience *",
      }),
    );
    expect(result.questions).toContainEqual(
      expect.objectContaining({ rawText: "Years of Experience *" }),
    );
  });

  it("does not promote unrelated focusable containers into application questions", () => {
    document.body.innerHTML = `<div tabindex="0">Help and support</div>`;
    const result = scanDocument();
    expect(result.questions).toHaveLength(0);
  });

  it("uses the radio-group prompt instead of Yes or No option labels", () => {
    document.body.innerHTML = `
      <div class="question-field">
        <p>Would you require any Visa sponsorship now or in the future? *</p>
        <label><input type="radio" name="sponsor" value="Yes"> Yes</label>
        <label><input type="radio" name="sponsor" value="No"> No</label>
      </div>
    `;
    const result = scanDocument();
    expect(result.questions).toHaveLength(1);
    expect(result.questions[0]).toMatchObject({
      rawText: "Would you require any Visa sponsorship now or in the future? *",
      semanticType: "SPONSORSHIP_FUTURE",
    });
  });

  it("captures bounded visible page text for AI job context", () => {
    document.body.innerHTML = `<main><h1>Recruiter</h1><p>Build relationships with candidates and clients.</p><label for="why">Why this role?</label><textarea id="why"></textarea></main>`;
    expect(scanDocument().pageContext).toContain(
      "Build relationships with candidates and clients.",
    );
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
  it("never reports a visibly populated aria-invalid field as satisfied", () => {
    document.body.innerHTML = `
      <label for="first-name">First Name *</label>
      <input id="first-name" type="text" required value="Aadil" aria-invalid="true">
    `;
    const control = scanDocument().controls.find(
      (candidate) => candidate.inputType === "text",
    );
    expect(control).toBeDefined();
    expect(control).toMatchObject({
      invalid: true,
      satisfied: false,
    });
  });



  it("keeps Voluntary Disclosures distinct from self-identification semantics", () => {
    document.body.innerHTML = `
      <main>
        <h2>Voluntary Disclosures</h2>
        <label for="gender">What is your gender? *</label>
        <select id="gender" required><option>Example choice</option></select>
        <label for="race">What is your race/ethnicity? *</label>
        <select id="race" required><option>Example choice</option></select>
        <label for="veteran">What is your veterans status? *</label>
        <select id="veteran" required><option>Example choice</option></select>
        <button type="button">Save and Continue</button>
      </main>
    `;

    const result = scanDocument();
    expect(result.applicationState).toBe("DISCLOSURES");
  });

  it("recognizes Self Identify as the EEO/self-identification page", () => {
    document.body.innerHTML = `
      <main>
        <h2>Self Identify</h2>
        <label for="name">Name *</label>
        <input id="name" required />
        <p>Voluntary Self-Identification of Disability</p>
        <label for="disability">Disability status *</label>
        <select id="disability" required><option>Example choice</option></select>
        <button type="button">Save and Continue</button>
      </main>
    `;

    const result = scanDocument();
    expect(result.applicationState).toBe("EEO");
  });

  it("keeps a structurally identified Review page distinct at final submit", () => {
    document.body.innerHTML = `
      <main>
        <h2>Review</h2>
        <p>Please review your application.</p>
        <button type="submit">Submit Application</button>
      </main>
    `;

    const result = scanDocument();
    expect(result.finalSubmissionBoundary).toBe(true);
    expect(result.applicationState).toBe("REVIEW");
    expect(result.navigationCandidates).toContainEqual(
      expect.objectContaining({ action: "FINAL_SUBMIT" }),
    );
  });

});
