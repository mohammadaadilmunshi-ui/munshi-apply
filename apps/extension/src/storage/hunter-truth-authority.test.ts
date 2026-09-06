import { describe, expect, it } from "vitest";
import type { ProfileFact } from "@munshi-apply/contracts";
import type {
  HunterApplicationTruthProjection,
  HunterTruthCache,
} from "@munshi-apply/contracts/career-os-phase8";
import {
  acceptHunterTruthProjection,
  loadHunterTruthCache,
  resolveApplicationFact,
  verifyHunterTruthProjectionIntegrity,
  type HunterTruthCacheStore,
} from "./hunter-truth-authority";

const EXPECTED_DIGEST =
  "4fb31c6fa280fed4a545d2684183887ae0fee874ade6d9df5d2136760e704b3d";
const STALE_EXPECTED_DIGEST =
  "f80be87d5fe5af7f89c86ac6c373ba324cb79257ccc8597e50f0e292f5ce8454";

function projection(
  overrides: Partial<HunterApplicationTruthProjection> = {},
): HunterApplicationTruthProjection {
  return {
    contract_version: "munshi-application-truth-projection-v1",
    authority: "munshi-hr-hunter",
    projection_mode: "READ_ONLY",
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
        category: "CONTACT",
        trust_level: "DOCUMENT_CONFIRMED",
        protected: false,
        source: "master-resume-extraction:extract-1",
        value: "candidate@example.com",
      },
      {
        fact_id: "fact-sponsorship",
        key: "application_defaults.sponsorship_required",
        category: "SPONSORSHIP",
        trust_level: "USER_CONFIRMED",
        protected: true,
        source: "candidate-profile-details-v31:r1",
        value_reference:
          "hunter-vault://candidate-profile-details-v31/sponsorship_required",
      },
    ],
    protected_fact_keys: ["application_defaults.sponsorship_required"],
    unresolved_fact_keys: ["application_defaults.work_modes"],
    mutation_authority: false,
    submission_authority: false,
    projection_digest: EXPECTED_DIGEST,
    ...overrides,
  };
}

function memoryStore(initial: HunterTruthCache | null = null): {
  store: HunterTruthCacheStore;
  read: () => HunterTruthCache | null;
} {
  let value = initial;
  return {
    store: {
      async load() {
        return value;
      },
      async save(cache) {
        value = cache;
      },
    },
    read: () => value,
  };
}

function proposal(key: string, value: ProfileFact["value"]): ProfileFact {
  return {
    factId: `proposal:${key}`,
    key,
    value,
    category: "WORK_PREFERENCE",
    trustLevel: "USER_CONFIRMED",
    source: "SIDE_PANEL",
    confirmedAt: "2026-09-06T00:31:00Z",
    updatedAt: "2026-09-06T00:31:00Z",
    protected: false,
  };
}

describe("Hunter Candidate Truth authority cache", () => {
  it("matches the Python canonical projection digest contract", async () => {
    const verified = await verifyHunterTruthProjectionIntegrity(projection());
    expect(verified.projection_digest).toBe(EXPECTED_DIGEST);
  });

  it("rejects a payload whose projected truth was modified without a new digest", async () => {
    const tampered = projection({
      facts: [
        {
          fact_id: "fact-email",
          key: "contact.email",
          category: "CONTACT",
          trust_level: "DOCUMENT_CONFIRMED",
          protected: false,
          source: "master-resume-extraction:extract-1",
          value: "attacker@example.com",
        },
        projection().facts[1],
      ],
    });
    await expect(
      verifyHunterTruthProjectionIntegrity(tampered),
    ).rejects.toThrow(/digest does not match/);
  });

  it("persists an initial verified Hunter projection and reads it back", async () => {
    const memory = memoryStore();
    const result = await acceptHunterTruthProjection(
      projection(),
      memory.store,
      new Date("2026-09-06T00:32:00Z"),
    );
    expect(result.disposition).toBe("INITIAL");
    expect(memory.read()?.source).toBe("munshi-hr-hunter");
    expect(
      (await loadHunterTruthCache(memory.store))?.projection.projection_digest,
    ).toBe(EXPECTED_DIGEST);
  });

  it("refuses stale Candidate Truth for the same immutable extraction scope", async () => {
    const memory = memoryStore();
    await acceptHunterTruthProjection(projection(), memory.store);

    const stale = projection({
      candidate_profile_binding: {
        ...projection().candidate_profile_binding,
        profile_revision: 3,
        profile_digest: "e".repeat(64),
      },
      projection_digest: STALE_EXPECTED_DIGEST,
    });
    await expect(
      acceptHunterTruthProjection(stale, memory.store),
    ).rejects.toThrow(/stale Hunter Candidate Truth/);
    expect(memory.read()?.projection.projection_digest).toBe(EXPECTED_DIGEST);
  });

  it("Hunter canonical truth wins over an Apply-local conflicting proposal", () => {
    const result = resolveApplicationFact(
      projection(),
      "contact.email",
      proposal("contact.email", "local@example.com"),
    );
    expect(result.status).toBe("RESOLVED");
    if (result.status !== "RESOLVED") throw new Error();
    expect(result.value).toBe("candidate@example.com");
    expect(result.authoritative).toBe(true);
  });

  it("uses a local user-confirmed value only as a proposal when Hunter is unknown", () => {
    const result = resolveApplicationFact(
      projection(),
      "application_defaults.work_modes",
      proposal("application_defaults.work_modes", ["remote", "hybrid"]),
    );
    expect(result.status).toBe("PROPOSAL_ONLY");
    if (result.status !== "PROPOSAL_ONLY") throw new Error();
    expect(result.requires_hunter_promotion).toBe(true);
    expect(result.authoritative).toBe(false);
  });

  it("does not let Apply plaintext override a protected Hunter fact", () => {
    const result = resolveApplicationFact(
      projection(),
      "application_defaults.sponsorship_required",
      proposal("application_defaults.sponsorship_required", false),
    );
    expect(result.status).toBe("PROTECTED_REFERENCE");
    if (result.status !== "PROTECTED_REFERENCE") throw new Error();
    expect(result.requires_secure_resolution).toBe(true);
    expect(result).not.toHaveProperty("value");
  });
});
