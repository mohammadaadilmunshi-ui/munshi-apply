import { describe, expect, it } from "vitest";
import {
  answerMemoryKey,
  canonicalAnswerMemoryKey,
  canAutoApproveRememberedAnswer,
  normalizeQuestionForMemory,
} from "./answer-memory";

describe("owner answer memory", () => {
  it("normalizes repeated employer questions without depending on punctuation or required markers", () => {
    expect(normalizeQuestionForMemory("  Are you Hispanic/Latino?*  ")).toBe(
      "are you hispanic latino",
    );
    expect(answerMemoryKey("ARE YOU HISPANIC / LATINO ?")).toBe(
      "are you hispanic latino",
    );
  });

  it("uses one semantic memory key for stable permanent questions with different wording", () => {
    expect(
      canonicalAnswerMemoryKey(
        "Will you now or in the future require sponsorship?",
        "SPONSORSHIP_FUTURE",
      ),
    ).toBe("semantic:SPONSORSHIP_FUTURE");
    expect(
      canonicalAnswerMemoryKey(
        "Do you require visa sponsorship in the future?",
        "SPONSORSHIP_FUTURE",
      ),
    ).toBe("semantic:SPONSORSHIP_FUTURE");
  });

  it("keeps company-specific narrative questions scoped to exact normalized wording", () => {
    expect(
      canonicalAnswerMemoryKey(
        "Why do you want to work for Example Company?",
        "WHY_COMPANY",
      ),
    ).toBe("question:why do you want to work for example company");
  });

  it("auto-approves exact short operational answers after owner approval", () => {
    expect(
      canAutoApproveRememberedAnswer({
        semanticType: "UNKNOWN",
        controlKind: "SELECT",
        value: "No",
      }),
    ).toBe(true);
  });

  it("allows exact short demographic recall only through the approved answer-memory path", () => {
    expect(
      canAutoApproveRememberedAnswer({
        semanticType: "VOLUNTARY_DEMOGRAPHIC",
        controlKind: "SELECT",
        value: "Decline to self-identify",
      }),
    ).toBe(true);
  });

  it("recalls context-specific narrative answers only as reviewable suggestions", () => {
    expect(
      canAutoApproveRememberedAnswer({
        semanticType: "WHY_COMPANY",
        controlKind: "TEXTAREA",
        value: "A previously approved answer",
      }),
    ).toBe(false);
  });

  it("never auto-approves long remembered prose", () => {
    expect(
      canAutoApproveRememberedAnswer({
        semanticType: "UNKNOWN",
        controlKind: "TEXTAREA",
        value: "x".repeat(501),
      }),
    ).toBe(false);
  });
});
