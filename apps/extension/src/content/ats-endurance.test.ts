// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { applyFillInstructions } from "./fill";
import { scanDocument } from "./scanner";

const visibleRectangle: DOMRect = {
  bottom: 40,
  height: 30,
  left: 10,
  right: 410,
  top: 10,
  width: 400,
  x: 10,
  y: 10,
  toJSON: () => ({}),
};

const timing = {
  optionTimeoutMs: 100,
  verificationTimeoutMs: 100,
  stabilityQuietMs: 5,
  stabilityTimeoutMs: 60,
  pollIntervalMs: 5,
};

function uniqueControlIds(): void {
  const page = scanDocument();
  const ids = page.controls.map((control) => control.controlId);
  expect(new Set(ids).size).toBe(ids.length);
}

function questionIdMatching(pattern: RegExp): string {
  const question = scanDocument().questions.find((candidate) =>
    pattern.test(candidate.rawText),
  );
  expect(question).toBeDefined();
  return question!.controlId;
}

beforeEach(() => {
  document.body.innerHTML = "";
  document.title = "Candidate Application";
  window.history.replaceState({}, "", "/apply");
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    visibleRectangle,
  );
});

describe("ATS-shaped browser endurance matrix", () => {
  it.each([
    [
      "Workday-style grouped fields",
      `
        <main data-automation-id="jobApplicationPage">
          <label for="email">Email Address *</label><input id="email" type="email" required>
          <fieldset><legend>Will you now or in the future require sponsorship?</legend>
            <label><input type="radio" name="sponsor" value="Yes">Yes</label>
            <label><input type="radio" name="sponsor" value="No">No</label>
          </fieldset>
          <button type="button">Save and Continue</button>
        </main>
      `,
      "NEXT",
    ],
    [
      "Greenhouse-style resume and narrative page",
      `
        <main id="application_form">
          <label for="resume">Resume/CV *</label><input id="resume" type="file" required>
          <label for="why">Why are you interested in this role?</label><textarea id="why"></textarea>
          <button type="button">Next</button>
        </main>
      `,
      "NEXT",
    ],
    [
      "Lever-style native fields",
      `
        <main class="application-page">
          <label for="name">Full name</label><input id="name">
          <label for="phone">Phone</label><input id="phone" type="tel">
          <label for="location">Current location</label><input id="location">
          <button type="button">Continue</button>
        </main>
      `,
      "NEXT",
    ],
    [
      "Ashby-style ARIA combobox",
      `
        <main>
          <label for="country">Country</label>
          <input id="country" role="combobox" aria-controls="countries" aria-expanded="false">
          <div id="countries" role="listbox"><div role="option">United States</div></div>
          <button type="button">Continue</button>
        </main>
      `,
      "NEXT",
    ],
    [
      "iCIMS-style validation page",
      `
        <main>
          <label for="email">Email</label>
          <input id="email" aria-invalid="true" aria-describedby="email-error">
          <div id="email-error">Email is required</div>
          <button type="button">Next</button>
        </main>
      `,
      "NEXT",
    ],
    [
      "Taleo-style native select",
      `
        <main>
          <label for="country">Country *</label>
          <select id="country" required><option>Choose</option><option>United States</option></select>
          <label><input type="checkbox"> I agree to the privacy notice</label>
          <button type="button">Continue</button>
        </main>
      `,
      "NEXT",
    ],
    [
      "SAP-style autocomplete",
      `
        <main>
          <label for="school">School or university</label>
          <input id="school" role="combobox" aria-controls="schools" autocomplete="off">
          <div id="schools" role="listbox"></div>
          <button type="button">Next</button>
        </main>
      `,
      "NEXT",
    ],
    [
      "SmartRecruiters-style review boundary",
      `
        <main>
          <h1>Review your application</h1>
          <button type="submit">Review and submit</button>
        </main>
      `,
      "FINAL_SUBMIT",
    ],
  ])("scans %s without losing control identity", (_label, html, action) => {
    document.body.innerHTML = html;
    const page = scanDocument();
    expect(page.controls.length).toBeGreaterThan(0);
    expect(
      page.navigationCandidates.some(
        (candidate) => candidate.action === action,
      ),
    ).toBe(true);
    uniqueControlIds();
  });

  it("fills and verifies a mixed Workday-style page, then rescans the accepted state", async () => {
    document.body.innerHTML = `
      <main data-automation-id="jobApplicationPage">
        <label for="email">Email Address *</label><input id="email" type="email" required>
        <label for="phone">Phone Number *</label><input id="phone" type="tel" required>
        <label for="country">Country *</label>
        <select id="country" required><option>Choose</option><option>United States</option></select>
        <fieldset><legend>Will you now or in the future require sponsorship?</legend>
          <label><input type="radio" name="sponsor" value="Yes">Yes</label>
          <label><input type="radio" name="sponsor" value="No">No</label>
        </fieldset>
        <button type="button">Save and Continue</button>
      </main>
    `;

    const results = await applyFillInstructions(
      [
        {
          controlId: questionIdMatching(/email/i),
          frameId: 0,
          value: "candidate@example.com",
          sensitive: false,
          approved: true,
        },
        {
          controlId: questionIdMatching(/phone/i),
          frameId: 0,
          value: "+1 856 555 0100",
          sensitive: false,
          approved: true,
        },
        {
          controlId: questionIdMatching(/country/i),
          frameId: 0,
          value: "United States",
          sensitive: false,
          approved: true,
        },
        {
          controlId: questionIdMatching(/sponsorship/i),
          frameId: 0,
          value: "No",
          sensitive: true,
          approved: true,
        },
      ],
      timing,
    );

    expect(results.map((result) => result.status)).toEqual([
      "FILLED",
      "FILLED",
      "FILLED",
      "FILLED",
    ]);
    expect((document.getElementById("email") as HTMLInputElement).value).toBe(
      "candidate@example.com",
    );
    expect(
      (document.getElementById("country") as HTMLSelectElement).value,
    ).toBe("United States");
    expect(
      document.querySelector<HTMLInputElement>("input[name='sponsor']:checked")
        ?.value,
    ).toBe("No");
    uniqueControlIds();
  });

  it("survives repeated dynamic conditional branches without duplicate control ids", () => {
    document.body.innerHTML = `
      <main id="application-root">
        <label for="authorized">Are you authorized to work in the United States?</label>
        <select id="authorized"><option>Choose</option><option>Yes</option><option>No</option></select>
        <div id="conditional"></div>
        <button type="button">Continue</button>
      </main>
    `;
    const conditional = document.getElementById("conditional")!;

    for (let cycle = 0; cycle < 75; cycle += 1) {
      conditional.innerHTML =
        cycle % 2 === 0
          ? `<label for="detail-${cycle}">Please explain</label><textarea id="detail-${cycle}"></textarea>`
          : "";
      const page = scanDocument();
      const ids = page.controls.map((control) => control.controlId);
      expect(new Set(ids).size).toBe(ids.length);
      expect(ids.length).toBeLessThanOrEqual(3);
    }
  });

  it("waits for a portaled async employer option and verifies the committed value", async () => {
    document.body.innerHTML = `
      <label for="city">City</label>
      <input id="city" role="combobox" aria-expanded="false" value="">
      <div id="portal-root"></div>
    `;
    const input = document.getElementById("city") as HTMLInputElement;
    const portal = document.getElementById("portal-root")!;
    input.addEventListener(
      "input",
      () => {
        setTimeout(() => {
          portal.innerHTML = `<div id="phl" role="option">Philadelphia</div>`;
          document.getElementById("phl")!.addEventListener("click", () => {
            input.value = "Philadelphia";
            document
              .getElementById("phl")!
              .setAttribute("aria-selected", "true");
          });
        }, 10);
      },
      { once: true },
    );

    const result = await applyFillInstructions(
      [
        {
          controlId: questionIdMatching(/city/i),
          frameId: 0,
          value: "Philadelphia",
          sensitive: false,
          approved: true,
        },
      ],
      timing,
    );

    expect(result[0]?.status).toBe("FILLED");
    expect(input.value).toBe("Philadelphia");
  });

  it("keeps OTP and final submission as owner-only boundaries", async () => {
    document.body.innerHTML = `
      <h1>Verify your account</h1>
      <label for="otp">One-time verification code</label>
      <input id="otp" autocomplete="one-time-code">
      <button type="submit">Submit application</button>
    `;
    const page = scanDocument();
    expect(page.securityCheckpoint).toBe("OTP");
    expect(page.finalSubmissionBoundary).toBe(true);
    expect(
      page.navigationCandidates.some(
        (candidate) => candidate.action === "FINAL_SUBMIT",
      ),
    ).toBe(true);
  });

  it("scans a very large application form while preserving unique stable identifiers", () => {
    const startedAt = performance.now();
    const fields = Array.from(
      { length: 300 },
      (_, index) =>
        `<label for="field-${index}">Application field ${index}</label><input id="field-${index}">`,
    ).join("");
    document.body.innerHTML = `<main>${fields}<button type="button">Continue</button></main>`;

    const first = scanDocument();
    const second = scanDocument();
    expect(first.controls).toHaveLength(301);
    expect(
      new Set(first.controls.map((control) => control.controlId)).size,
    ).toBe(301);
    expect(second.controls.map((control) => control.controlId)).toEqual(
      first.controls.map((control) => control.controlId),
    );
    if (process.env.MUNSHI_PERF_STRICT === "1") {
      expect(performance.now() - startedAt).toBeLessThan(5_000);
    }
  }, 10_000);
});
