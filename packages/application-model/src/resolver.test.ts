import type {
  MasterProfile,
  ProfileFact,
  Question,
} from "@munshi-apply/contracts";
import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { describe, expect, it } from "vitest";
import { factKeyForSemanticType, resolveProfileAnswer } from "./resolver";

const now = "2026-08-14T18:00:00.000Z";

function fact(overrides: Partial<ProfileFact>): ProfileFact {
  return {
    factId: "fact-1",
    key: "first_name",
    value: "Aadil",
    category: "IDENTITY",
    trustLevel: "USER_CONFIRMED",
    source: "profile",
    confirmedAt: now,
    updatedAt: now,
    protected: false,
    ...overrides,
  };
}

function profile(facts: ProfileFact[]): MasterProfile {
  return {
    profileId: "profile-1",
    displayName: "Test profile",
    facts,
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
  };
}

function snapshot(
  records: ProfileSnapshot["records"],
  facts: ProfileFact[] = [],
): ProfileSnapshot {
  return {
    ...profile(facts),
    records,
    recordTombstones: [],
    snapshotVersion: 1,
  };
}

function question(overrides: Partial<Question>): Question {
  return {
    questionId: "question-1",
    controlId: "control-1",
    rawText: "First name",
    semanticType: "FIRST_NAME",
    confidence: 0.94,
    sensitive: false,
    requiresReview: false,
    ...overrides,
  };
}

describe("factKeyForSemanticType", () => {
  it("keeps current sponsorship separate from other immigration facts", () => {
    expect(factKeyForSemanticType("SPONSORSHIP_CURRENT")).toBe(
      "current_sponsorship",
    );
    expect(factKeyForSemanticType("SPONSORSHIP_FUTURE")).toBe(
      "future_sponsorship",
    );
    expect(factKeyForSemanticType("IMMIGRATION_ASSISTANCE")).toBe(
      "immigration_assistance",
    );
  });
});

describe("resolveProfileAnswer", () => {
  it("marks a trusted ordinary fact ready", () => {
    const result = resolveProfileAnswer(
      question({}),
      profile([fact({ protected: false })]),
    );

    expect(result).toMatchObject({
      state: "READY",
      value: "Aadil",
      sourceKey: "first_name",
      sensitive: false,
      protected: false,
    });
  });

  it("allows explicitly confirmed ordinary protected identity facts", () => {
    const result = resolveProfileAnswer(
      question({ semanticType: "FIRST_NAME", rawText: "First Name *" }),
      profile([fact({ protected: true, confirmedAt: now })]),
    );
    expect(result.state).toBe("READY");
    expect(result.value).toBe("Aadil");
    expect(result.protected).toBe(true);
  });

  it("still reviews an ordinary protected identity fact without confirmation", () => {
    const result = resolveProfileAnswer(
      question({ semanticType: "FIRST_NAME", rawText: "First Name *" }),
      profile([fact({ protected: true, confirmedAt: null })]),
    );
    expect(result.state).toBe("REVIEW");
    expect(result.reasons).toContain(
      "Protected source fact has not been explicitly confirmed",
    );
  });

  it("forces protected facts through review even when confirmed", () => {
    const result = resolveProfileAnswer(
      question({
        rawText: "Do you currently require sponsorship?",
        semanticType: "SPONSORSHIP_CURRENT",
        sensitive: true,
        requiresReview: true,
      }),
      profile([
        fact({
          key: "current_sponsorship",
          value: "No",
          category: "SPONSORSHIP",
          protected: true,
        }),
      ]),
    );

    expect(result.state).toBe("REVIEW");
    expect(result.sourceKey).toBe("current_sponsorship");
    expect(result.reasons).toContain("Source fact is protected");
  });

  it("does not promote generated facts to ready answers", () => {
    const result = resolveProfileAnswer(
      question({}),
      profile([fact({ trustLevel: "GENERATED" })]),
    );

    expect(result.state).toBe("REVIEW");
    expect(result.reasons[0]).toContain(
      "non-authoritative trust level GENERATED",
    );
  });

  it("leaves unmapped written questions unresolved", () => {
    const result = resolveProfileAnswer(
      question({ semanticType: "WHY_COMPANY", rawText: "Why this company?" }),
      profile([fact({})]),
    );

    expect(result.state).toBe("UNRESOLVED");
    expect(result.value).toBeNull();
  });

  it("leaves missing profile facts unresolved instead of inventing an answer", () => {
    const result = resolveProfileAnswer(question({}), profile([]));

    expect(result).toMatchObject({
      state: "UNRESOLVED",
      sourceKey: "first_name",
      value: null,
    });
  });

  it("resolves repeatable records in explicit profile order", () => {
    const result = resolveProfileAnswer(
      question({ semanticType: "SCHOOL_NAME", rawText: "University name" }),
      snapshot([
        {
          recordId: "education-2",
          kind: "EDUCATION",
          label: "Second school",
          facts: [
            fact({
              factId: "school-2",
              key: "school_name",
              value: "Second school",
              category: "EDUCATION",
            }),
          ],
          sortOrder: 1,
          createdAt: now,
          updatedAt: now,
        },
        {
          recordId: "education-1",
          kind: "EDUCATION",
          label: "First school",
          facts: [
            fact({
              factId: "school-1",
              key: "school_name",
              value: "First school",
              category: "EDUCATION",
            }),
          ],
          sortOrder: 0,
          createdAt: now,
          updatedAt: now,
        },
      ]),
    );

    expect(result).toMatchObject({
      state: "READY",
      value: "First school",
      sourceFactId: "school-1",
      sourceKey: "school_name",
    });
  });

  it("prefers canonical record facts and falls back to legacy flat facts", () => {
    const legacyEmployer = fact({
      factId: "legacy-employer",
      key: "current_employer",
      value: "Legacy employer",
      category: "EMPLOYMENT",
    });
    const recordEmployer = fact({
      factId: "record-employer",
      key: "employer_name",
      value: "Canonical employer",
      category: "EMPLOYMENT",
    });
    const employerQuestion = question({
      semanticType: "EMPLOYER_NAME",
      rawText: "Current employer",
    });
    const canonical = snapshot(
      [
        {
          recordId: "employment-1",
          kind: "EMPLOYMENT",
          label: "Canonical employer",
          facts: [recordEmployer],
          sortOrder: 0,
          createdAt: now,
          updatedAt: now,
        },
      ],
      [legacyEmployer],
    );

    expect(resolveProfileAnswer(employerQuestion, canonical).value).toBe(
      "Canonical employer",
    );
    expect(
      resolveProfileAnswer(employerQuestion, snapshot([], [legacyEmployer]))
        .value,
    ).toBe("Legacy employer");
  });
});
