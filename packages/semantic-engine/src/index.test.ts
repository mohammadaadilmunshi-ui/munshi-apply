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

  it("classifies common deterministic contact questions", () => {
    expect(classifyQuestion("Email address").semanticType).toBe("EMAIL");
    expect(classifyQuestion("Mobile phone").semanticType).toBe("PHONE");
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
