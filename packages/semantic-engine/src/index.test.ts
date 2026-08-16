import { describe, expect, it } from "vitest";
import { classifyQuestion } from "./index";

describe("classifyQuestion", () => {
  it("classifies required-marker identity labels from live ATS forms", () => {
    expect(classifyQuestion("First Name *").semanticType).toBe("FIRST_NAME");
    expect(classifyQuestion("Last Name*").semanticType).toBe("LAST_NAME");
    expect(classifyQuestion("Preferred Pronouns *").semanticType).toBe(
      "PRONOUNS",
    );
  });

  it("classifies future sponsorship as sensitive and reviewable", () => {
    expect(
      classifyQuestion("Will you now or in the future require sponsorship?"),
    ).toMatchObject({
      semanticType: "SPONSORSHIP_FUTURE",
      sensitive: true,
      requiresReview: true,
    });
    expect(
      classifyQuestion(
        "Would you require any Visa sponsorship now or in the future (this includes OPT for F1 students, J1 visas, or M1 visas)?",
      ),
    ).toMatchObject({
      semanticType: "SPONSORSHIP_FUTURE",
      sensitive: true,
      requiresReview: true,
      matchedRule: "future-sponsorship",
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

  it("recognizes live ATS availability wording", () => {
    expect(
      classifyQuestion("Are you available to start on September 29, 2026 *"),
    ).toMatchObject({ semanticType: "START_DATE", matchedRule: "start-date" });
    expect(
      classifyQuestion("When are you available to start this role? *"),
    ).toMatchObject({ semanticType: "START_DATE", matchedRule: "start-date" });
  });

  it("recognizes recruitment-role screening and written prompts", () => {
    expect(
      classifyQuestion(
        "Would this be your first experience working in a professional recruitment role? *",
      ),
    ).toMatchObject({
      semanticType: "RELEVANT_EXPERIENCE",
      matchedRule: "first-recruitment-role",
    });
    expect(
      classifyQuestion(
        "How would you describe 360° recruitment and what are the key responsibilities of the position? *",
      ),
    ).toMatchObject({
      semanticType: "WHY_ROLE",
      matchedRule: "role-understanding",
    });
    expect(
      classifyQuestion(
        "What motivates you to pursue a career in recruitment or sales? *",
      ),
    ).toMatchObject({
      semanticType: "CAREER_GOALS",
      matchedRule: "career-motivation",
    });
  });

  it("recognizes live graduation and career-transition prompts", () => {
    expect(
      classifyQuestion(
        "When did you / when do you Graduate from University? *",
      ),
    ).toMatchObject({
      semanticType: "GRADUATION_DATE",
      matchedRule: "graduation",
    });
    expect(
      classifyQuestion("Why are you looking to leave your current employer? *"),
    ).toMatchObject({
      semanticType: "CAREER_GOALS",
      matchedRule: "leave-current-employer",
    });
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
