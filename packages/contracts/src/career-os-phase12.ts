import { z } from "zod";
import { FactCategorySchema, TrustLevelSchema } from "./index";

export const PROFILE_SNAPSHOT_VERSION =
  "munshi-candidate-profile-snapshot-v1" as const;
export const EXECUTION_RECEIPT_VERSION =
  "munshi-apply-execution-receipt-v1" as const;
export const PROFILE_AUTHORITY = "munshi-hr-hunter" as const;
export const APPLY_EVENT_SOURCE = "munshi-apply" as const;

const Sha256Schema = z.string().regex(/^[a-f0-9]{64}$/);
const FactValueSchema = z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.array(z.string()),
]);

const ProfileFactBaseSchema = z.object({
  fact_id: z.string().min(1).max(128),
  key: z.string().min(1).max(256),
  category: FactCategorySchema,
  trust_level: TrustLevelSchema,
  source: z.string().min(1).max(256),
});

export const HunterProfileFactSchema = z.discriminatedUnion("protected", [
  ProfileFactBaseSchema.extend({
    protected: z.literal(false),
    value: FactValueSchema,
    value_reference: z.never().optional(),
  }).strict(),
  ProfileFactBaseSchema.extend({
    protected: z.literal(true),
    value_reference: z.string().min(1).max(256),
    value: z.never().optional(),
  }).strict(),
]);
export type HunterProfileFact = z.infer<typeof HunterProfileFactSchema>;

export const HunterProfileSnapshotSchema = z
  .object({
    contract_version: z.literal(PROFILE_SNAPSHOT_VERSION),
    authority: z.literal(PROFILE_AUTHORITY),
    projection_mode: z.literal("READ_ONLY"),
    tenant_id: z.string().min(1).max(128),
    user_id: z.string().min(1).max(128),
    profile_id: z.string().min(1).max(128),
    profile_revision: z.number().int().positive(),
    source_extraction_id: z.string().min(1).max(128),
    generated_at: z.string().datetime({ offset: true }),
    facts: z.array(HunterProfileFactSchema),
    profile_digest: Sha256Schema,
  })
  .strict()
  .superRefine((snapshot, context) => {
    const factIds = new Set<string>();
    for (const fact of snapshot.facts) {
      if (factIds.has(fact.fact_id)) {
        context.addIssue({
          code: "custom",
          message: `Duplicate profile fact id: ${fact.fact_id}`,
          path: ["facts"],
        });
      }
      factIds.add(fact.fact_id);
    }
  });
export type HunterProfileSnapshot = z.infer<typeof HunterProfileSnapshotSchema>;

export const HunterResumeArtifactSchema = z
  .object({
    artifact_id: z.string().min(1).max(128),
    kind: z.string().min(1).max(64),
    sha256: Sha256Schema,
    mime_type: z.string().min(1).max(128),
    size_bytes: z.number().int().nonnegative().optional(),
    source_preparation_id: z.string().min(1).max(128),
    profile_revision: z.number().int().positive(),
    job_id: z.string().min(1).max(128),
  })
  .strict();
export type HunterResumeArtifact = z.infer<typeof HunterResumeArtifactSchema>;

export const applyExecutionEventTypes = [
  "APPLICATION_READY",
  "CHECKPOINT_REQUIRED",
  "SECURITY_CHECKPOINT",
  "INTERACTION_FAILED",
  "RECOVERY_SUCCEEDED",
  "APPLICATION_SUBMITTED",
  "APPLICATION_CONFIRMED",
  "APPLICATION_COMPLETED",
] as const;
export const ApplyExecutionEventTypeSchema = z.enum(applyExecutionEventTypes);
export type ApplyExecutionEventType = z.infer<
  typeof ApplyExecutionEventTypeSchema
>;

export const ApplyExecutionReceiptSchema = z
  .object({
    contract_version: z.literal(EXECUTION_RECEIPT_VERSION),
    source: z.literal(APPLY_EVENT_SOURCE),
    event_id: z.string().min(1).max(128),
    correlation_id: z.string().min(1).max(128),
    tenant_id: z.string().min(1).max(128),
    user_id: z.string().min(1).max(128),
    handoff_id: z.string().min(1).max(128),
    preparation_id: z.string().min(1).max(128),
    application_id: z.string().min(1).max(128),
    runtime_application_id: z.string().min(1).max(256),
    provider: z.string().min(1).max(64),
    event_type: ApplyExecutionEventTypeSchema,
    occurred_at: z.string().datetime({ offset: true }),
    payload: z.record(z.string(), z.unknown()),
  })
  .strict()
  .superRefine((receipt, context) => {
    if (receipt.event_type === "APPLICATION_SUBMITTED") {
      if (
        receipt.payload.submit_attempted !== true ||
        receipt.payload.submit_succeeded !== true
      ) {
        context.addIssue({
          code: "custom",
          message:
            "APPLICATION_SUBMITTED requires verified successful submit evidence",
          path: ["payload"],
        });
      }
    }

    if (
      receipt.event_type === "APPLICATION_CONFIRMED" ||
      receipt.event_type === "APPLICATION_COMPLETED"
    ) {
      if (receipt.payload.confirmation_observed !== true) {
        context.addIssue({
          code: "custom",
          message: `${receipt.event_type} requires confirmation evidence`,
          path: ["payload"],
        });
      }
    }
  });
export type ApplyExecutionReceipt = z.infer<typeof ApplyExecutionReceiptSchema>;

export function eventCanAssertSubmission(
  value: unknown,
): value is ApplyExecutionReceipt {
  const parsed = ApplyExecutionReceiptSchema.safeParse(value);
  if (!parsed.success) return false;
  return (
    parsed.data.event_type === "APPLICATION_SUBMITTED" ||
    parsed.data.event_type === "APPLICATION_CONFIRMED" ||
    parsed.data.event_type === "APPLICATION_COMPLETED"
  );
}
