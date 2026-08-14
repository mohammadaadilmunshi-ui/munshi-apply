import { describe, expect, it } from "vitest";
import { classifyQuestion } from "./index";

describe("classifyQuestion", () => {
  it("classifies future sponsorship as sensitive and reviewable", () => {
    expect(
      classifyQuestion("Will you now or in the future require sponsorship?"),
    ).toMatchObject({
      semanticType: "SPONSORSHIP_FUTURE",
      sensitive: true,
      requiresReview: true,
    });
  });

  it("classifies explicit current sponsorship as a dedicated protected concept", () => {
    expect(
      classifyQuestion("Do you currently require sponsorship?"),
    ).toMatchObject({
      semanticType: "SPONSORSHIP_CURRENT",
      sensitive: true,
      requiresReview: true,
      matchedRule: "current-sponsorship",
    });
  });

  it("keeps ambiguous generic sponsorship wording manual", () => {
    expect(classifyQuestion("Do you require sponsorship?")).toMatchObject({
      semanticType: "UNKNOWN",
      sensitive: true,
      requiresReview: true,
      matchedRule: "sponsorship",
    });
  });

  it("forces explicit approval for other high-risk questions", () => {
    expect(classifyQuestion("Desired salary")).toMatchObject({
      semanticType: "SALARY_EXPECTATION",
      sensitive: true,
      requiresReview: true,
    });
    expect(classifyQuestion("Full legal name")).toMatchObject({
      semanticType: "PERSONAL",
      sensitive: true,
      requiresReview: true,
    });
  });

  it("classifies common deterministic contact questions", () => {
    expect(classifyQuestion("Email address").semanticType).toBe("EMAIL");
    expect(classifyQuestion("Mobile phone").semanticType).toBe("PHONE");
  });

  it("distinguishes recurring identity and address fields", () => {
    expect(classifyQuestion("First name").semanticType).toBe("FIRST_NAME");
    expect(classifyQuestion("Middle initial").semanticType).toBe("MIDDLE_NAME");
    expect(classifyQuestion("Last name").semanticType).toBe("LAST_NAME");
    expect(classifyQuestion("Preferred name").semanticType).toBe(
      "PREFERRED_NAME",
    );
    expect(classifyQuestion("Street address").semanticType).toBe(
      "STREET_ADDRESS",
    );
    expect(classifyQuestion("ZIP code").semanticType).toBe("POSTAL_CODE");
    expect(classifyQuestion("Country").semanticType).toBe("COUNTRY");
  });

  it("recognizes recurring education and employment identity fields", () => {
    expect(classifyQuestion("University name").semanticType).toBe(
      "SCHOOL_NAME",
    );
    expect(classifyQuestion("Current employer").semanticType).toBe(
      "EMPLOYER_NAME",
    );
    expect(classifyQuestion("Job title").semanticType).toBe("JOB_TITLE");
  });

  it("recognizes reusable preference and credential fields", () => {
    expect(classifyQuestion("Notice period").semanticType).toBe(
      "NOTICE_PERIOD",
    );
    expect(classifyQuestion("Relevant skills").semanticType).toBe("SKILLS");
    expect(classifyQuestion("Certifications").semanticType).toBe(
      "CERTIFICATIONS",
    );
    expect(classifyQuestion("Languages spoken").semanticType).toBe("LANGUAGES");
    expect(classifyQuestion("How did you hear about us?").semanticType).toBe(
      "REFERRAL",
    );
  });

  it("leaves novel questions unknown instead of inventing a meaning", () => {
    expect(classifyQuestion("Name your favorite constellation")).toEqual({
      semanticType: "UNKNOWN",
      confidence: 0.35,
      sensitive: false,
      requiresReview: true,
      matchedRule: null,
    });
  });
});
