import { describe, expect, it } from "vitest";
import {
  APPLICATION_TRUTH_VERSION,
  HunterApplicationTruthProjectionSchema,
  classifyHunterTruthUpdate,
  projectionMatchesBinding,
  resolveCanonicalHunterFact,
} from "./career-os-phase8";

function projection(overrides: Record<string, unknown> = {}) {
  return {
    contract_version: APPLICATION_TRUTH_VERSION,
    authority: "munshi-hr-hunter" as const,
    projection_mode: "READ_ONLY" as const,
    tenant_id: "tenant-1",
    user_id: "user-1",
    profile_id: "candidate-truth:tenant-1:user-1",
    candidate_profile_binding: {
      source_extraction_id: "extract-1",
      profile_revision: 4,
      profile_digest: "a".repeat(64),
      source_profile_sha256: "b".repeat(64),
      source_resume_sha256: "c".repeat(64),
    },
    generated_at: "2026-09-06T00:30:00Z",
    job_context: null,
    facts: [
      {
        fact_id: "fact-email",
        key: "contact.email",
        category: "CONTACT" as const,
        trust_level: "DOCUMENT_CONFIRMED" as const,
        protected: false as const,
        source: "master-resume-extraction:extract-1",
        value: "candidate@example.com",
      },
      {
        fact_id: "fact-sponsorship",
        key: "application_defaults.sponsorship_required",
        category: "SPONSORSHIP" as const,
        trust_level: "USER_CONFIRMED" as const,
        protected: true as const,
        source: "candidate-profile-details-v31:r1",
        value_reference:
          "hunter-vault://candidate-profile-details-v31/sponsorship_required",
      },
    ],
    protected_fact_keys: ["application_defaults.sponsorship_required"],
    unresolved_fact_keys: ["application_defaults.work_modes"],
    mutation_authority: false as const,
    submission_authority: false as const,
    projection_digest: "d".repeat(64),
    ...overrides,
  };
}

describe("Phase 8 Hunter Candidate Truth consumer", () => {
  it("accepts only Hunter-owned read-only non-submitting projections", () => {
    const parsed = HunterApplicationTruthProjectionSchema.parse(projection());
    expect(parsed.authority).toBe("munshi-hr-hunter");
    expect(parsed.projection_mode).toBe("READ_ONLY");
    expect(parsed.mutation_authority).toBe(false);
    expect(parsed.submission_authority).toBe(false);

    expect(() =>
      HunterApplicationTruthProjectionSchema.parse({
        ...projection(),
        authority: "munshi-apply",
      }),
    ).toThrow();
    expect(() =>
      HunterApplicationTruthProjectionSchema.parse({
        ...projection(),
        submission_authority: true,
      }),
    ).toThrow();
  });

  it("requires protected inventory to exactly match protected projected facts", () => {
    expect(() =>
      HunterApplicationTruthProjectionSchema.parse({
        ...projection(),
        protected_fact_keys: [],
      }),
    ).toThrow(/Protected fact key inventory/);
  });

  it("never exposes protected Candidate Truth as generic plaintext", () => {
    const protectedFact = resolveCanonicalHunterFact(
      projection(),
      "application_defaults.sponsorship_required",
    );
    expect(protectedFact.status).toBe("PROTECTED_REFERENCE");
    if (protectedFact.status !== "PROTECTED_REFERENCE") throw new Error();
    expect(protectedFact.requires_secure_resolution).toBe(true);
    expect(protectedFact.value_reference).toContain("hunter-vault://");
    expect(protectedFact).not.toHaveProperty("value");
  });

  it("resolves normal Hunter truth and leaves absent facts unknown", () => {
    const email = resolveCanonicalHunterFact(projection(), "contact.email");
    expect(email.status).toBe("RESOLVED");
    if (email.status !== "RESOLVED") throw new Error();
    expect(email.value).toBe("candidate@example.com");
    expect(email.authoritative).toBe(true);

    expect(
      resolveCanonicalHunterFact(projection(), "application_defaults.salary"),
    ).toEqual({
      status: "UNKNOWN",
      key: "application_defaults.salary",
      authoritative: false,
      requires_secure_resolution: false,
    });
  });

  it("does not allow a stale same-extraction projection to replace current truth", () => {
    const current = projection();
    const stale = projection({
      candidate_profile_binding: {
        ...current.candidate_profile_binding,
        profile_revision: 3,
        profile_digest: "e".repeat(64),
      },
      projection_digest: "f".repeat(64),
    });
    expect(classifyHunterTruthUpdate(current, stale)).toBe("STALE_INCOMING");
  });

  it("treats same revision with different content as a conflict", () => {
    const current = projection();
    const conflict = projection({
      candidate_profile_binding: {
        ...current.candidate_profile_binding,
        profile_digest: "e".repeat(64),
      },
      projection_digest: "f".repeat(64),
    });
    expect(classifyHunterTruthUpdate(current, conflict)).toBe("CONFLICT");
  });

  it("allows a new Master Resume extraction scope without comparing revision numbers", () => {
    const current = projection();
    const replacement = projection({
      candidate_profile_binding: {
        ...current.candidate_profile_binding,
        source_extraction_id: "extract-2",
        profile_revision: 1,
        profile_digest: "e".repeat(64),
      },
      projection_digest: "f".repeat(64),
    });
    expect(classifyHunterTruthUpdate(current, replacement)).toBe("REPLACE");
  });

  it("binds application work to the exact Hunter Candidate Truth state", () => {
    const current = projection();
    expect(
      projectionMatchesBinding(current, current.candidate_profile_binding),
    ).toBe(true);
    expect(
      projectionMatchesBinding(current, {
        ...current.candidate_profile_binding,
        profile_digest: "e".repeat(64),
      }),
    ).toBe(false);
  });
});
