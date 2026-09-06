import { describe, expect, it } from "vitest";
import {
  ApplyExecutionReceiptSchema,
  EXECUTION_RECEIPT_VERSION,
  HunterProfileSnapshotSchema,
  HunterResumeArtifactSchema,
  PROFILE_SNAPSHOT_VERSION,
  compositeProfileRevision,
  eventCanAssertSubmission,
  profileDigestPayload,
  validateReceiptCorrelation,
} from "./career-os-phase12";

function plainFact() {
  return {
    fact_id: "fact-name",
    key: "identity.full_name",
    category: "IDENTITY" as const,
    trust_level: "USER_CONFIRMED" as const,
    protected: false as const,
    source: "candidate-truth-profile",
    value: "Example Candidate",
  };
}

function protectedFact() {
  return {
    fact_id: "fact-auth",
    key: "work_authorization.detail",
    category: "WORK_AUTHORIZATION" as const,
    trust_level: "USER_CONFIRMED" as const,
    protected: true as const,
    source: "candidate-override-vault",
    value_reference: "vault://profile/profile-1/fact-auth",
  };
}

function profileSnapshot() {
  const overrideRevision = 3;
  const candidateDetailsRevision = 2;
  return {
    contract_version: PROFILE_SNAPSHOT_VERSION,
    authority: "munshi-hr-hunter" as const,
    projection_mode: "READ_ONLY" as const,
    revision_scope: "SOURCE_EXTRACTION" as const,
    tenant_id: "owner",
    user_id: "owner-user",
    profile_id: "profile-1",
    profile_revision: compositeProfileRevision(
      overrideRevision,
      candidateDetailsRevision,
    ),
    override_revision: overrideRevision,
    candidate_details_revision: candidateDetailsRevision,
    source_extraction_id: "extract-3",
    source_profile_sha256: "a".repeat(64),
    source_resume_sha256: "b".repeat(64),
    generated_at: "2026-09-05T20:30:00Z",
    facts: [plainFact(), protectedFact()],
    profile_digest: "c".repeat(64),
  };
}

function receipt(eventType: string, payload: Record<string, unknown> = {}) {
  return {
    contract_version: EXECUTION_RECEIPT_VERSION,
    source: "munshi-apply",
    event_id: `event-${eventType.toLowerCase()}`,
    correlation_id: "correlation-1",
    tenant_id: "owner",
    user_id: "owner-user",
    handoff_id: "handoff-1",
    handoff_body_sha256: "d".repeat(64),
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
  it("accepts only a read-only Hunter-owned evidence-bound profile projection", () => {
    const parsed = HunterProfileSnapshotSchema.parse(profileSnapshot());
    expect(parsed.authority).toBe("munshi-hr-hunter");
    expect(parsed.revision_scope).toBe("SOURCE_EXTRACTION");
    expect(parsed.source_profile_sha256).toHaveLength(64);
    expect(parsed.source_resume_sha256).toHaveLength(64);

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
    expect(() =>
      HunterProfileSnapshotSchema.parse({
        ...profileSnapshot(),
        revision_scope: "GLOBAL",
      }),
    ).toThrow();
  });

  it("requires profile revision to match the two encrypted Section 1 revisions", () => {
    const snapshot = profileSnapshot();
    expect(snapshot.profile_revision).toBe(compositeProfileRevision(3, 2));
    expect(() =>
      HunterProfileSnapshotSchema.parse({
        ...snapshot,
        profile_revision: snapshot.profile_revision + 1,
      }),
    ).toThrow(/revision components/);
  });

  it("defines stable profile digest state without export timestamp metadata", () => {
    const snapshot = HunterProfileSnapshotSchema.parse(profileSnapshot());
    const payload = profileDigestPayload(snapshot);
    expect(payload).not.toHaveProperty("generated_at");
    expect(payload).not.toHaveProperty("profile_digest");
    expect(payload.source_extraction_id).toBe("extract-3");
    expect(payload.override_revision).toBe(3);
    expect(payload.candidate_details_revision).toBe(2);
  });

  it("rejects protected fact plaintext, duplicate ids, and duplicate keys", () => {
    const protectedWithPlaintext = profileSnapshot();
    protectedWithPlaintext.facts = [
      plainFact(),
      {
        ...protectedFact(),
        value: "must-not-cross-generic-contract",
      } as never,
    ];
    expect(() =>
      HunterProfileSnapshotSchema.parse(protectedWithPlaintext),
    ).toThrow();

    const duplicateId = profileSnapshot();
    duplicateId.facts = [plainFact(), { ...plainFact() }];
    expect(() => HunterProfileSnapshotSchema.parse(duplicateId)).toThrow(
      /Duplicate profile fact id/,
    );

    const duplicateKey = profileSnapshot();
    duplicateKey.facts = [
      plainFact(),
      {
        ...protectedFact(),
        key: plainFact().key,
      },
    ];
    expect(() => HunterProfileSnapshotSchema.parse(duplicateKey)).toThrow(
      /Duplicate profile fact key/,
    );
  });

  it("requires an exact resume hash plus exact profile snapshot binding", () => {
    const artifact = HunterResumeArtifactSchema.parse({
      artifact_id: "resume-1",
      kind: "resume_pdf",
      sha256: "b".repeat(64),
      mime_type: "application/pdf",
      size_bytes: 12345,
      source_preparation_id: "prep-1",
      source_extraction_id: "extract-3",
      profile_revision: compositeProfileRevision(3, 2),
      profile_digest: "c".repeat(64),
      job_id: "job-1",
    });
    expect(artifact.sha256).toHaveLength(64);
    expect(artifact.profile_digest).toHaveLength(64);
    expect(() =>
      HunterResumeArtifactSchema.parse({ ...artifact, sha256: "not-a-digest" }),
    ).toThrow();
    expect(() =>
      HunterResumeArtifactSchema.parse({
        ...artifact,
        profile_digest: "not-a-digest",
      }),
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

  it("blocks submission or confirmation claims on the wrong event type", () => {
    expect(() =>
      ApplyExecutionReceiptSchema.parse(
        receipt("APPLICATION_READY", { submit_succeeded: true }),
      ),
    ).toThrow(/Non-submission/);
    expect(() =>
      ApplyExecutionReceiptSchema.parse(
        receipt("APPLICATION_READY", { confirmation_observed: true }),
      ),
    ).toThrow(/Non-confirmation/);
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

  it("binds reverse receipts to the exact Hunter handoff context", () => {
    const ready = receipt("APPLICATION_READY");
    expect(
      validateReceiptCorrelation(ready, {
        tenant_id: "owner",
        user_id: "owner-user",
        handoff_id: "handoff-1",
        handoff_body_sha256: "d".repeat(64),
        preparation_id: "prep-1",
        application_id: "application-1",
      }).handoff_id,
    ).toBe("handoff-1");

    expect(() =>
      validateReceiptCorrelation(ready, {
        tenant_id: "owner",
        user_id: "owner-user",
        handoff_id: "handoff-1",
        handoff_body_sha256: "e".repeat(64),
        preparation_id: "prep-1",
        application_id: "application-1",
      }),
    ).toThrow(/handoff_body_sha256/);
  });

  it("keeps checkpoints and failures non-submitted", () => {
    expect(eventCanAssertSubmission(receipt("SECURITY_CHECKPOINT"))).toBe(
      false,
    );
    expect(eventCanAssertSubmission(receipt("INTERACTION_FAILED"))).toBe(false);
  });
});
