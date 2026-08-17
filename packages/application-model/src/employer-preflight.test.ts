import { describe, expect, it } from "vitest";
import type {
  ApplicationPage,
  ProfileFact,
} from "@munshi-apply/contracts";
import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import {
  buildEmployerPreflightReport,
  evaluateCurrentPageKnockouts,
  extractEmployerRequirements,
  parseSalaryRange,
} from "./employer-preflight";

const now = "2026-08-17T19:00:00.000Z";

function page(overrides: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-preflight",
    tabId: 1,
    frameId: 0,
    documentId: "doc-preflight",
    url: "https://example.com/apply",
    title: "Apply",
    pageContext: "Application form",
    observedAt: now,
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: "fingerprint",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    ...overrides,
  };
}

function fact(
  key: string,
  value: string,
  options: Partial<ProfileFact> = {},
): ProfileFact {
  return {
    factId: `fact-${key}`,
    key,
    value,
    category: "SAVED_ANSWER",
    trustLevel: "USER_CONFIRMED",
    source: "TEST",
    confirmedAt: now,
    updatedAt: now,
    protected: false,
    ...options,
  };
}

function profile(facts: ProfileFact[]): ProfileSnapshot {
  return {
    profileId: "profile-1",
    displayName: "Profile",
    facts,
    records: [],
    recordTombstones: [],
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

describe("employer preflight intelligence", () => {
  it("extracts an explicit no-sponsorship knockout but not a generic question", () => {
    const current = page({
      pageContext:
        "Candidates must be authorized to work in the United States. We do not offer visa sponsorship for this position.",
      questions: [
        {
          questionId: "q-sponsor",
          controlId: "sponsor",
          rawText: "Will you now or in the future require sponsorship?",
          semanticType: "SPONSORSHIP_FUTURE",
          confidence: 1,
          sensitive: true,
          requiresReview: true,
        },
      ],
    });
    const requirements = extractEmployerRequirements(current);
    expect(
      requirements.filter((item) => item.kind === "SPONSORSHIP"),
    ).toHaveLength(1);
    expect(
      requirements.find((item) => item.kind === "SPONSORSHIP")?.expectedValues,
    ).toEqual(["No"]);
    expect(
      requirements.find((item) => item.kind === "WORK_AUTHORIZATION")?.expectedValues,
    ).toEqual(["Yes"]);
  });

  it("blocks a confirmed sponsorship answer that conflicts with an explicit rule", () => {
    const current = page({
      pageContext: "This employer does not offer visa sponsorship.",
      questions: [
        {
          questionId: "q-sponsor",
          controlId: "sponsor",
          rawText: "Will you require sponsorship?",
          semanticType: "SPONSORSHIP_FUTURE",
          confidence: 1,
          sensitive: true,
          requiresReview: true,
        },
      ],
    });
    const report = buildEmployerPreflightReport(
      current,
      profile([
        fact("future_sponsorship", "Yes", {
          category: "SPONSORSHIP",
          protected: true,
        }),
      ]),
    );
    expect(report.findings[0]?.state).toBe("BLOCKED");
    expect(report.gate.state).toBe("BLOCKED");

    const live = evaluateCurrentPageKnockouts(current, {
      "q-sponsor": { value: "Yes", approved: true },
    });
    expect(live).toHaveLength(1);
    expect(live[0]?.state).toBe("BLOCKED");
  });

  it("marks an explicit no-sponsorship rule ready when the confirmed answer is No", () => {
    const current = page({
      pageContext: "No visa sponsorship is available for this role.",
      questions: [
        {
          questionId: "q-sponsor",
          controlId: "sponsor",
          rawText: "Will you require sponsorship?",
          semanticType: "SPONSORSHIP_FUTURE",
          confidence: 1,
          sensitive: true,
          requiresReview: true,
        },
      ],
    });
    const report = buildEmployerPreflightReport(
      current,
      profile([
        fact("future_sponsorship", "No", {
          category: "SPONSORSHIP",
          protected: true,
        }),
      ]),
    );
    expect(report.findings[0]?.state).toBe("READY");
    expect(report.gate.state).toBe("READY");
  });

  it("compares explicit degree minimums without inventing equivalency", () => {
    const current = page({
      pageContext: "A bachelor's degree is required for this role.",
    });
    const meets = buildEmployerPreflightReport(
      current,
      profile([
        fact("highest_degree", "Master of Science", {
          category: "EDUCATION",
          protected: true,
        }),
      ]),
    );
    expect(meets.findings[0]?.state).toBe("READY");

    const misses = buildEmployerPreflightReport(
      current,
      profile([
        fact("highest_degree", "Associate degree", {
          category: "EDUCATION",
          protected: true,
        }),
      ]),
    );
    expect(misses.findings[0]?.state).toBe("BLOCKED");
  });

  it("reviews experience thresholds instead of guessing tenure from résumé dates", () => {
    const current = page({
      pageContext: "At least 3 years of professional experience is required.",
    });
    const report = buildEmployerPreflightReport(
      current,
      profile([
        fact("employment_summary", "Recruiting and HR operations experience", {
          category: "EMPLOYMENT",
        }),
      ]),
    );
    expect(report.findings[0]?.state).toBe("REVIEW");
    expect(report.findings[0]?.reason).toMatch(/will not infer total tenure/i);
  });

  it("keeps salary compatibility as review intelligence rather than an auto-reject", () => {
    const current = page({
      pageContext: "Base salary: $80,000 to $100,000 annually.",
    });
    expect(parseSalaryRange(current.pageContext ?? "")).toEqual({
      minimum: 80_000,
      maximum: 100_000,
      currency: "USD",
      period: "YEAR",
    });
    const report = buildEmployerPreflightReport(
      current,
      profile([fact("salary_expectation", "Salary expectation: $90,000 annually")]),
    );
    expect(report.findings[0]?.state).toBe("REVIEW");
    expect(report.findings[0]?.reason).toMatch(/overlap/i);
  });

  it("blocks an explicit citizenship requirement when the confirmed fact is incompatible", () => {
    const current = page({
      pageContext: "United States citizenship is required for this position.",
    });
    const report = buildEmployerPreflightReport(
      current,
      profile([
        fact("citizenship", "Indian citizen", {
          category: "IDENTITY",
          protected: true,
        }),
      ]),
    );
    expect(report.findings[0]?.state).toBe("BLOCKED");
  });

  it("returns an empty ready report when there is no explicit employer requirement", () => {
    const report = buildEmployerPreflightReport(
      page({ pageContext: "Join our collaborative people team." }),
      profile([]),
    );
    expect(report.requirements).toEqual([]);
    expect(report.findings).toEqual([]);
    expect(report.gate.state).toBe("READY");
  });
});
