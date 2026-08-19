import type { ProfileFact, Question } from "@munshi-apply/contracts";
import type {
  ProfileRecord,
  ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";
import { describe, expect, it } from "vitest";
import { resolveProfileAnswer } from "./resolver";

const now = "2026-08-16T05:45:00.000Z";

function fact(
  key: string,
  value: string,
  category: ProfileFact["category"] = "EMPLOYMENT",
): ProfileFact {
  return {
    factId: `${key}-${value}`,
    key,
    value,
    category,
    trustLevel: "USER_CONFIRMED",
    source: "profile",
    confirmedAt: now,
    updatedAt: now,
    protected: false,
  };
}

function record(
  kind: ProfileRecord["kind"],
  id: string,
  sortOrder: number,
  facts: ProfileFact[],
): ProfileRecord {
  return {
    recordId: id,
    kind,
    label: id,
    facts,
    sortOrder,
    createdAt: now,
    updatedAt: now,
  };
}

function snapshot(records: ProfileRecord[]): ProfileSnapshot {
  return {
    profileId: "profile-1",
    displayName: "Aadil",
    facts: [],
    records,
    recordTombstones: [],
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

function question(
  semanticType: Question["semanticType"],
  rawText: string,
  repeatIndex = 0,
): Question {
  return {
    questionId: `${semanticType}-${repeatIndex}`,
    controlId: `${semanticType}-${repeatIndex}`,
    rawText,
    contextText: "Work History",
    semanticType,
    confidence: 0.94,
    sensitive: false,
    requiresReview: false,
    repeatIndex,
  };
}

const toyota = record("EMPLOYMENT", "toyota", 0, [
  fact("employer_name", "Toyota Connected India"),
  fact("job_title", "Human Resource Recruitment & Operations Intern"),
  fact("employment_start_date", "2024-07-01"),
  fact("employment_end_date", "2025-01-31"),
]);

const familyBusiness = record("EMPLOYMENT", "family-business", 1, [
  fact("employer_name", "Family Business"),
  fact("job_title", "Part-Time HR Recruiter"),
  fact("employment_start_date", "2023-01-01"),
  fact("employment_end_date", "2024-06-30"),
]);

describe("repeatable application record resolution", () => {
  it("resolves employment start and end dates instead of availability dates", () => {
    const profile = snapshot([toyota]);
    expect(
      resolveProfileAnswer(
        question("EMPLOYMENT_START_DATE", "Start date"),
        profile,
      ).value,
    ).toBe("2024-07-01");
    expect(
      resolveProfileAnswer(question("EMPLOYMENT_END_DATE", "End date"), profile)
        .value,
    ).toBe("2025-01-31");
  });

  it("selects the matching repeated employment record", () => {
    const result = resolveProfileAnswer(
      question("EMPLOYER_NAME", "Company", 1),
      snapshot([toyota, familyBusiness]),
    );
    expect(result.value).toBe("Family Business");
  });

  it("derives Bain company industry from authoritative employer identity", () => {
    const result = resolveProfileAnswer(
      question("COMPANY_INDUSTRY", "Company Industry"),
      snapshot([toyota]),
    );
    expect(result).toMatchObject({
      state: "READY",
      value: "Automotive & Mobility",
      sourceKey: "employer_name",
    });
  });

  it("derives Bain position function from authoritative HR role evidence", () => {
    const result = resolveProfileAnswer(
      question("POSITION_FUNCTION", "Position Function"),
      snapshot([toyota]),
    );
    expect(result).toMatchObject({
      state: "READY",
      value: "Human Capital",
      sourceKey: "job_title",
    });
  });

  it("resolves education start dates from education records", () => {
    const education = record("EDUCATION", "masters", 0, [
      fact("school_name", "Montclair State University", "EDUCATION"),
      fact("degree", "Master of Science", "EDUCATION"),
      fact("education_start_date", "2025-09-01", "EDUCATION"),
      fact("graduation_date", "2026-12-16", "EDUCATION"),
    ]);
    const educationQuestion: Question = {
      ...question("EDUCATION_START_DATE", "Start Date"),
      contextText: "Education History",
    };
    expect(
      resolveProfileAnswer(educationQuestion, snapshot([education])).value,
    ).toBe("2025-09-01");
  });
});
