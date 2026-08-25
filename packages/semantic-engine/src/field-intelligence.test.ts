import { describe, expect, it } from "vitest";
import { classifyQuestion } from "./field-intelligence";

describe("semantic field equivalence", () => {
  it("unwraps common prompt wording without requiring exact label text", () => {
    expect(classifyQuestion("Please enter your full name *")).toMatchObject({
      semanticType: "PERSONAL",
      sensitive: true,
      requiresReview: true,
      matchedRule: "prompt-full-name",
    });
    expect(classifyQuestion("What is your current employer?")).toMatchObject({
      semanticType: "EMPLOYER_NAME",
      matchedRule: "prompt-employer-name",
    });
    expect(classifyQuestion("Please provide your email address")).toMatchObject(
      {
        semanticType: "EMAIL",
        matchedRule: "prompt-email",
      },
    );
  });

  it("recognizes common deterministic aliases", () => {
    expect(classifyQuestion("Applicant Name").semanticType).toBe("PERSONAL");
    expect(classifyQuestion("Legal first name").semanticType).toBe(
      "FIRST_NAME",
    );
    expect(classifyQuestion("Cell phone number").semanticType).toBe("PHONE");
    expect(classifyQuestion("Organization name").semanticType).toBe(
      "EMPLOYER_NAME",
    );
    expect(classifyQuestion("Role title").semanticType).toBe("JOB_TITLE");
  });

  it("uses strong field metadata when visible wording is generic", () => {
    expect(
      classifyQuestion("Name", "candidateInformation firstName given-name"),
    ).toMatchObject({
      semanticType: "FIRST_NAME",
      matchedRule: "metadata-first-name",
    });
    expect(
      classifyQuestion("Contact", "candidateForm mobilePhone tel"),
    ).toMatchObject({
      semanticType: "PHONE",
      matchedRule: "metadata-phone",
    });
    expect(
      classifyQuestion("Location", "addressForm postalCode postal-code"),
    ).toMatchObject({
      semanticType: "POSTAL_CODE",
      matchedRule: "metadata-postal-code",
    });
  });

  it("preserves high-risk review rules after wording normalization", () => {
    expect(
      classifyQuestion(
        "Please confirm whether you now or in the future require sponsorship?",
      ),
    ).toMatchObject({
      semanticType: "SPONSORSHIP_FUTURE",
      sensitive: true,
      requiresReview: true,
    });
  });

  it("does not reinterpret unrelated prompts merely because they contain a common word", () => {
    expect(classifyQuestion("Name your favorite constellation")).toMatchObject({
      semanticType: "UNKNOWN",
      matchedRule: null,
    });
  });
});
