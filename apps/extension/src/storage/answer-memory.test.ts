import { describe, expect, it } from "vitest";
import {
  answerMemoryKey,
  canAutoApproveRememberedAnswer,
  normalizeQuestionForMemory,
} from "./answer-memory";

describe("owner answer memory", () => {
  it("normalizes repeated employer questions without depending on punctuation or required markers", () => {
    expect(
      normalizeQuestionForMemory("  Are you Hispanic/Latino?*  "),
    ).toBe("are you hispanic latino");
    expect(answerMemoryKey("ARE YOU HISPANIC / LATINO ?")).toBe(
      "are you hispanic latino",
    );
  });

  it("auto-approves exact short operational answers", () => {
    expect(
      canAutoApproveRememberedAnswer({
        semanticType: "UNKNOWN",
        controlKind: "SELECT",
        value: "No",
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
});
