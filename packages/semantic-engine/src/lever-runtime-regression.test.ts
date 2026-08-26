import { describe, expect, it } from "vitest";
import { classifyQuestion } from "./index";

describe("Lever runtime semantic regressions", () => {
  it("recognizes Unicode-marked full name", () => {
    expect(classifyQuestion("Full name✱").semanticType).toBe("PERSONAL");
  });

  it("recognizes plural future sponsorship wording", () => {
    expect(
      classifyQuestion(
        "Will you now or in the future require any visa sponsorships or transfers for employment in the US?✱",
      ).semanticType,
    ).toBe("SPONSORSHIP_FUTURE");
  });

  it("recognizes common current company and location aliases", () => {
    expect(classifyQuestion("Current company").semanticType).toBe(
      "EMPLOYER_NAME",
    );
    expect(classifyQuestion("Current location✱").semanticType).toBe(
      "CURRENT_LOCATION",
    );
  });

  it("keeps GitHub distinct from a portfolio URL", () => {
    expect(classifyQuestion("GitHub URL").semanticType).toBe("GITHUB");
    expect(classifyQuestion("Other website").semanticType).toBe("WEBSITE");
  });
});
