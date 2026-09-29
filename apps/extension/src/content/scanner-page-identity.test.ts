// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import { scanDocument } from "./scanner";

describe("scanner application page identity", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Application";
  });

  it("changes page identity when an explicit job query changes", () => {
    window.history.replaceState({}, "", "/apply?job=123");
    const first = scanDocument();

    window.history.replaceState({}, "", "/apply?job=456");
    const second = scanDocument();

    expect(first.pageId).not.toBe(second.pageId);
    expect(first.documentId).not.toBe(second.documentId);
  });

  it("changes page identity across SPA application steps on the same URL", () => {
    window.history.replaceState({}, "", "/apply?job=123");
    document.body.innerHTML = `
      <main>
        <h2>My Information</h2>
        <label>First Name <input name="first_name" /></label>
        <button type="button">Save and Continue</button>
      </main>
    `;
    const personal = scanDocument();

    document.body.innerHTML = `
      <main>
        <h2>My Experience</h2>
        <label>Employer <input name="employer" /></label>
        <button type="button">Save and Continue</button>
      </main>
    `;
    const experience = scanDocument();

    expect(personal.applicationState).toBe("PERSONAL");
    expect(experience.applicationState).toBe("EXPERIENCE");
    expect(personal.pageId).not.toBe(experience.pageId);
    expect(personal.documentId).toBe(experience.documentId);
  });
  it("keeps page identity stable when only tracking parameters change", () => {
    window.history.replaceState({}, "", "/apply?job=123&utm_source=a");
    const first = scanDocument();

    window.history.replaceState({}, "", "/apply?job=123&utm_source=b");
    const second = scanDocument();

    expect(first.pageId).toBe(second.pageId);
    expect(first.documentId).toBe(second.documentId);
  });
});
