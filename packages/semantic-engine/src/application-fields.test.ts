import { describe, expect, it } from "vitest";
import { classifyQuestion } from "./index";

describe("expanded application field semantics", () => {
  it("classifies broad education-level prompts as degree fields", () => {
    expect(
      classifyQuestion("Highest level of education obtained or in progress")
        .semanticType,
    ).toBe("DEGREE");
  });

  it("classifies Bain employment taxonomy controls", () => {
    expect(classifyQuestion("Company Industry").semanticType).toBe(
      "COMPANY_INDUSTRY",
    );
    expect(classifyQuestion("Position Function").semanticType).toBe(
      "POSITION_FUNCTION",
    );
  });

  it("uses section context to disambiguate identical Start date labels", () => {
    expect(classifyQuestion("Start date", "Education History").semanticType).toBe(
      "EDUCATION_START_DATE",
    );
    expect(classifyQuestion("Start date", "Work History").semanticType).toBe(
      "EMPLOYMENT_START_DATE",
    );
  });

  it("uses work-history context to identify employment end dates", () => {
    expect(classifyQuestion("End date", "Work History").semanticType).toBe(
      "EMPLOYMENT_END_DATE",
    );
  });
});
