import type {
  MasterProfile,
  ProfileFact,
  Question,
} from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import { resolveProfileAnswer } from "./resolver-smart";

const now = "2026-08-25T08:15:00.000Z";

function fact(
  key: string,
  value: string,
  overrides: Partial<ProfileFact> = {},
): ProfileFact {
  return {
    factId: `fact-${key}`,
    key,
    value,
    category: "IDENTITY",
    trustLevel: "USER_CONFIRMED",
    source: "SIDE_PANEL",
    confirmedAt: now,
    updatedAt: now,
    protected: true,
    ...overrides,
  };
}

function profile(facts: ProfileFact[]): MasterProfile {
  return {
    profileId: "profile-1",
    displayName: "Profile",
    facts,
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
  };
}

function fullNameQuestion(): Question {
  return {
    questionId: "question-full-name",
    controlId: "control-full-name",
    rawText: "Full Name",
    semanticType: "PERSONAL",
    confidence: 0.94,
    sensitive: true,
    requiresReview: true,
  };
}

describe("smart profile resolver", () => {
  it("uses an explicitly confirmed legal name without asking again", () => {
    const result = resolveProfileAnswer(
      fullNameQuestion(),
      profile([fact("legal_name", "Aadil Munshi")]),
    );

    expect(result).toMatchObject({
      state: "READY",
      value: "Aadil Munshi",
      sourceKey: "legal_name",
      sensitive: true,
      protected: true,
    });
  });

  it("composes a full name from confirmed name components when legal_name is absent", () => {
    const result = resolveProfileAnswer(
      fullNameQuestion(),
      profile([
        fact("first_name", "Mohammad"),
        fact("middle_name", "Aadil"),
        fact("last_name", "Munshi"),
      ]),
    );

    expect(result).toMatchObject({
      state: "READY",
      value: "Mohammad Aadil Munshi",
      sourceKey: "first_name+middle_name+last_name",
      sensitive: true,
      protected: true,
    });
  });

  it("does not compose a protected name from unconfirmed components", () => {
    const result = resolveProfileAnswer(
      fullNameQuestion(),
      profile([
        fact("first_name", "Mohammad"),
        fact("last_name", "Munshi", { confirmedAt: null }),
      ]),
    );

    expect(result.state).toBe("UNRESOLVED");
  });

  it("keeps unrelated high-risk questions on the existing policy path", () => {
    const question: Question = {
      ...fullNameQuestion(),
      rawText: "Will you now or in the future require sponsorship?",
      semanticType: "SPONSORSHIP_FUTURE",
    };
    const result = resolveProfileAnswer(
      question,
      profile([
        fact("future_sponsorship", "Yes", {
          category: "SPONSORSHIP",
          confirmedAt: null,
        }),
      ]),
    );

    expect(result.state).toBe("REVIEW");
  });
});
