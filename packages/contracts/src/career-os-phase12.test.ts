import { describe, expect, it } from "vitest";
import {
  ApplyExecutionReceiptSchema,
  EXECUTION_RECEIPT_VERSION,
  HunterProfileSnapshotSchema,
  HunterResumeArtifactSchema,
  PROFILE_SNAPSHOT_VERSION,
  eventCanAssertSubmission,
} from "./career-os-phase12";

function profileSnapshot() {
  return {
    contract_version: PROFILE_SNAPSHOT_VERSION,
    authority: "munshi-hr-hunter" as const,
    projection_mode: "READ_ONLY" as const,
    tenant_id: "owner",
    user_id: "owner-user",
    profile_id: "profile-1",
    profile_revision: 7,
    source_extraction_id: "extract-3",
    generated_at: "2026-09-05T20:30:00Z",
    facts: [
      {
        fact_id: "fact-name",
        key: "identity.full_name",
        category: "IDENTITY" as const,
        trust_level: "USER_CONFIRMED" as const,
        protected: false as const,
        source: "candidate-truth-profile",
        value: "Example Candidate",
      },
      {
        fact_id: "fact-auth",
        key: "work_authorization.detail",
        category: "WORK_AUTHORIZATION" as const,
        trust_level: "USER_CONFIRMED" as const,
        protected: true as const,
        source: "candidate-override-vault",
        value_reference: "vault://profile/profile-1/fact-auth",
      },
    ],
    profile_digest: "a".repeat(64),
  };
}

function receipt(eventType: string, payload: Record<string, unknown> = {}) {
  return {
    contract_version: EXECUTION_RECEIPT_VERSION,
    source: "munshi-apply",
    event_id: `event-${eventType.toLowerCase()}`,
    correlation_id: "handoff-1",
    tenant_id: "owner",
    user_id: "owner-user",
    handoff_id: "handoff-1",
    preparation_id: "prep-1",
    application_id: "application-1",
    runtime_application_id: "runtime-application-1",
    provider: "GREENHOUSE",
    event_type: eventType,
    occurred_at: "2026-09-05T20:31:00Z",
    payload,
  };
}

describe("Career OS Phase 12 wire contracts", () => {
  it("accepts only a read-only Hunter-owned profile projection", () => {
    expect(HunterProfileSnapshotSchema.parse(profileSnapshot()).authority).toBe(
      "munshi-hr-hunter",
    );
    expect(() =>
      HunterProfileSnapshotSchema.parse({
        ...profileSnapshot(),
        authority: "munshi-apply",
      }),
    ).toThrow();
    expect(() =>
      HunterProfileSnapshotSchema.parse({
        ...profileSnapshot(),
        projection_mode: "READ_WRITE",
      }),
    ).toThrow();
  });

  it("rejects protected fact plaintext and duplicate fact ids", () => {
    const protectedWithPlaintext = profileSnapshot();
    protectedWithPlaintext.facts[1] = {
      ...protectedWithPlaintext.facts[1],
      value: "must-not-cross-generic-contract",
    } as never;
    expect(() =>
      HunterProfileSnapshotSchema.parse(protectedWithPlaintext),
    ).toThrow();

    const duplicate = profileSnapshot();
    duplicate.facts = [duplicate.facts[0], { ...duplicate.facts[0] }];
    expect(() => HunterProfileSnapshotSchema.parse(duplicate)).toThrow(
      /Duplicate profile fact id/,
    );
  });

  it("requires an exact lowercase SHA-256 for Hunter resume artifacts", () => {
    const artifact = HunterResumeArtifactSchema.parse({
      artifact_id: "resume-1",
      kind: "resume_pdf",
      sha256: "b".repeat(64),
      mime_type: "application/pdf",
      size_bytes: 12345,
      source_preparation_id: "prep-1",
      profile_revision: 7,
      job_id: "job-1",
    });
    expect(artifact.sha256).toHaveLength(64);
    expect(() =>
      HunterResumeArtifactSchema.parse({ ...artifact, sha256: "not-a-digest" }),
    ).toThrow();
  });

  it("does not treat handoff acceptance, readiness, or Gmail as submission", () => {
    expect(() =>
      ApplyExecutionReceiptSchema.parse({
        ...receipt("APPLICATION_READY"),
        source: "gmail",
      }),
    ).toThrow();
    expect(() =>
      ApplyExecutionReceiptSchema.parse(receipt("HANDOFF_ACCEPTED")),
    ).toThrow();
    expect(eventCanAssertSubmission(receipt("APPLICATION_READY"))).toBe(false);
  });

  it("requires verified successful submit evidence", () => {
    expect(() =>
      ApplyExecutionReceiptSchema.parse(receipt("APPLICATION_SUBMITTED")),
    ).toThrow(/verified successful submit evidence/);
    expect(
      eventCanAssertSubmission(
        receipt("APPLICATION_SUBMITTED", {
          submit_attempted: true,
          submit_succeeded: true,
        }),
      ),
    ).toBe(true);
  });

  it("requires confirmation evidence for confirmed/completed events", () => {
    expect(() =>
      ApplyExecutionReceiptSchema.parse(receipt("APPLICATION_CONFIRMED")),
    ).toThrow(/confirmation evidence/);
    expect(
      eventCanAssertSubmission(
        receipt("APPLICATION_CONFIRMED", { confirmation_observed: true }),
      ),
    ).toBe(true);
  });

  it("keeps checkpoints and failures non-submitted", () => {
    expect(eventCanAssertSubmission(receipt("SECURITY_CHECKPOINT"))).toBe(
      false,
    );
    expect(eventCanAssertSubmission(receipt("INTERACTION_FAILED"))).toBe(false);
  });
});
