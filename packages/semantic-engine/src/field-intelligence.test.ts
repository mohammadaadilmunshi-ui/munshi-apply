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
  it("keeps segmented phone metadata controls separate from the phone number", () => {
    expect(
      classifyQuestion(
        "Phone Device Type Select One Required",
        "phoneNumber--phoneType",
      ),
    ).toMatchObject({
      semanticType: "PHONE_DEVICE_TYPE",
      matchedRule: "phone-device-type",
    });
    expect(
      classifyQuestion(
        "Country Phone Code",
        "phoneNumber--countryPhoneCode",
      ),
    ).toMatchObject({
      semanticType: "PHONE_COUNTRY_CODE",
    });
    expect(
      classifyQuestion("Phone Extension", "phoneNumber--extension"),
    ).toMatchObject({
      semanticType: "PHONE_EXTENSION",
      matchedRule: "phone-extension",
    });
    expect(
      classifyQuestion("Phone Number", "phoneNumber--phoneNumber"),
    ).toMatchObject({
      semanticType: "PHONE",
    });
  });

  it("classifies common eligibility, self-id, and legal application prompts", () => {
    expect(
      classifyQuestion("Are you at least 18 years of age?"),
    ).toMatchObject({
      semanticType: "AGE_18_PLUS",
      sensitive: true,
      requiresReview: true,
    });
    expect(
      classifyQuestion(
        "Are you eligible to work in the location in which this position is located?",
      ),
    ).toMatchObject({
      semanticType: "WORK_LOCATION_ELIGIBILITY",
      sensitive: true,
      requiresReview: true,
    });
    expect(
      classifyQuestion("Do you identify as Hispanic or Latino?"),
    ).toMatchObject({
      semanticType: "HISPANIC_LATINO",
      sensitive: true,
      requiresReview: true,
    });
    expect(
      classifyQuestion("Employee ID (if applicable)"),
    ).toMatchObject({
      semanticType: "EMPLOYEE_ID",
      sensitive: true,
      requiresReview: true,
    });
    expect(
      classifyQuestion("I accept the Terms and Conditions."),
    ).toMatchObject({
      semanticType: "LEGAL_ATTESTATION",
      requiresReview: true,
    });
  });

  it("uses self-identification context to distinguish generic name and date fields", () => {
    expect(
      classifyQuestion(
        "Name",
        "Voluntary Self-Identification of Disability Form CC-305",
      ),
    ).toMatchObject({
      semanticType: "SELF_ID_NAME",
    });
    expect(
      classifyQuestion(
        "Date",
        "Voluntary Self-Identification of Disability Form CC-305",
      ),
    ).toMatchObject({
      semanticType: "SELF_ID_DATE",
    });
  });


});
