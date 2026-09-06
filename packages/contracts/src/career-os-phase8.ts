import { z } from "zod";
import {
  HunterProfileFactSchema,
  HunterProfileSnapshotSchema,
  PROFILE_AUTHORITY,
} from "./career-os-phase12";

export const APPLICATION_TRUTH_VERSION =
  "munshi-application-truth-projection-v1" as const;
export const APPLICATION_TRUTH_CACHE_VERSION =
  "munshi-apply-hunter-truth-cache-v1" as const;

const Sha256Schema = z.string().regex(/^[a-f0-9]{64}$/);

export const CandidateProfileBindingSchema = z
  .object({
    source_extraction_id: z.string().min(1).max(128),
    profile_revision: z.number().int().positive(),
    profile_digest: Sha256Schema,
    source_profile_sha256: Sha256Schema,
    source_resume_sha256: Sha256Schema,
  })
  .strict();
export type CandidateProfileBinding = z.infer<
  typeof CandidateProfileBindingSchema
>;

export const ApplicationTruthJobContextSchema = z
  .object({
    job_id: z.string().min(1).max(128),
    job_snapshot_sha256: Sha256Schema,
  })
  .strict();
export type ApplicationTruthJobContext = z.infer<
  typeof ApplicationTruthJobContextSchema
>;

export const HunterApplicationTruthProjectionSchema = z
  .object({
    contract_version: z.literal(APPLICATION_TRUTH_VERSION),
    authority: z.literal(PROFILE_AUTHORITY),
    projection_mode: z.literal("READ_ONLY"),
    tenant_id: z.string().min(1).max(128),
    user_id: z.string().min(1).max(128),
    profile_id: z.string().min(1).max(128),
    candidate_profile_binding: CandidateProfileBindingSchema,
    generated_at: z.string().datetime({ offset: true }),
    job_context: ApplicationTruthJobContextSchema.nullable(),
    facts: z.array(HunterProfileFactSchema),
    protected_fact_keys: z.array(z.string().min(1).max(256)),
    unresolved_fact_keys: z.array(z.string().min(1).max(256)),
    mutation_authority: z.literal(false),
    submission_authority: z.literal(false),
    projection_digest: Sha256Schema,
  })
  .strict()
  .superRefine((projection, context) => {
    const protectedKeys = projection.facts
      .filter((fact) => fact.protected)
      .map((fact) => fact.key)
      .sort();
    const declaredProtected = [...projection.protected_fact_keys].sort();
    if (JSON.stringify(protectedKeys) !== JSON.stringify(declaredProtected)) {
      context.addIssue({
        code: "custom",
        message: "Protected fact key inventory does not match projected facts",
        path: ["protected_fact_keys"],
      });
    }

    const factKeys = new Set(projection.facts.map((fact) => fact.key));
    for (const key of projection.unresolved_fact_keys) {
      if (factKeys.has(key)) {
        context.addIssue({
          code: "custom",
          message: `Resolved fact cannot also be unresolved: ${key}`,
          path: ["unresolved_fact_keys"],
        });
      }
    }
  });
export type HunterApplicationTruthProjection = z.infer<
  typeof HunterApplicationTruthProjectionSchema
>;

export const HunterTruthCacheSchema = z
  .object({
    cache_version: z.literal(APPLICATION_TRUTH_CACHE_VERSION),
    source: z.literal(PROFILE_AUTHORITY),
    cached_at: z.string().datetime({ offset: true }),
    projection: HunterApplicationTruthProjectionSchema,
  })
  .strict();
export type HunterTruthCache = z.infer<typeof HunterTruthCacheSchema>;

export type HunterTruthUpdateDisposition =
  | "INITIAL"
  | "UNCHANGED"
  | "REPLACE"
  | "STALE_INCOMING"
  | "CONFLICT";

export function classifyHunterTruthUpdate(
  currentValue: unknown,
  incomingValue: unknown,
): HunterTruthUpdateDisposition {
  const incoming = HunterApplicationTruthProjectionSchema.parse(incomingValue);
  if (currentValue === null || currentValue === undefined) return "INITIAL";
  const current = HunterApplicationTruthProjectionSchema.parse(currentValue);

  if (
    current.tenant_id !== incoming.tenant_id ||
    current.user_id !== incoming.user_id ||
    current.profile_id !== incoming.profile_id
  ) {
    return "CONFLICT";
  }
  if (current.projection_digest === incoming.projection_digest) {
    return "UNCHANGED";
  }

  const currentBinding = current.candidate_profile_binding;
  const incomingBinding = incoming.candidate_profile_binding;
  if (
    currentBinding.source_extraction_id === incomingBinding.source_extraction_id
  ) {
    if (incomingBinding.profile_revision < currentBinding.profile_revision) {
      return "STALE_INCOMING";
    }
    if (incomingBinding.profile_revision === currentBinding.profile_revision) {
      return "CONFLICT";
    }
  }
  // A different extraction ID represents a new immutable Master Resume evidence
  // scope. Numeric revisions are intentionally not compared across scopes.
  return "REPLACE";
}

export type CanonicalFactResolution =
  | {
      status: "UNKNOWN";
      key: string;
      authoritative: false;
      requires_secure_resolution: false;
    }
  | {
      status: "PROTECTED_REFERENCE";
      key: string;
      authoritative: true;
      requires_secure_resolution: true;
      value_reference: string;
      trust_level: z.infer<typeof HunterProfileFactSchema>["trust_level"];
      source: string;
    }
  | {
      status: "RESOLVED";
      key: string;
      authoritative: true;
      requires_secure_resolution: false;
      value: string | number | boolean | string[];
      trust_level: z.infer<typeof HunterProfileFactSchema>["trust_level"];
      source: string;
    };

export function resolveCanonicalHunterFact(
  projectionValue: unknown,
  key: string,
): CanonicalFactResolution {
  const projection = HunterApplicationTruthProjectionSchema.parse(projectionValue);
  const normalizedKey = key.trim();
  const fact = projection.facts.find((candidate) => candidate.key === normalizedKey);
  if (!fact) {
    return {
      status: "UNKNOWN",
      key: normalizedKey,
      authoritative: false,
      requires_secure_resolution: false,
    };
  }
  if (fact.protected) {
    return {
      status: "PROTECTED_REFERENCE",
      key: normalizedKey,
      authoritative: true,
      requires_secure_resolution: true,
      value_reference: fact.value_reference,
      trust_level: fact.trust_level,
      source: fact.source,
    };
  }
  return {
    status: "RESOLVED",
    key: normalizedKey,
    authoritative: true,
    requires_secure_resolution: false,
    value: fact.value,
    trust_level: fact.trust_level,
    source: fact.source,
  };
}

export function projectionMatchesBinding(
  projectionValue: unknown,
  bindingValue: unknown,
): boolean {
  const projection = HunterApplicationTruthProjectionSchema.parse(projectionValue);
  const binding = CandidateProfileBindingSchema.parse(bindingValue);
  const current = projection.candidate_profile_binding;
  return (
    current.source_extraction_id === binding.source_extraction_id &&
    current.profile_revision === binding.profile_revision &&
    current.profile_digest === binding.profile_digest &&
    current.source_profile_sha256 === binding.source_profile_sha256 &&
    current.source_resume_sha256 === binding.source_resume_sha256
  );
}

/**
 * Validate that an embedded Candidate Truth snapshot and Phase 8 projection refer
 * to exactly the same Hunter-owned candidate state. Useful at handoff boundaries.
 */
export function projectionMatchesHunterSnapshot(
  projectionValue: unknown,
  snapshotValue: unknown,
): boolean {
  const projection = HunterApplicationTruthProjectionSchema.parse(projectionValue);
  const snapshot = HunterProfileSnapshotSchema.parse(snapshotValue);
  return (
    projection.tenant_id === snapshot.tenant_id &&
    projection.user_id === snapshot.user_id &&
    projection.profile_id === snapshot.profile_id &&
    projection.candidate_profile_binding.source_extraction_id ===
      snapshot.source_extraction_id &&
    projection.candidate_profile_binding.profile_revision ===
      snapshot.profile_revision &&
    projection.candidate_profile_binding.profile_digest === snapshot.profile_digest
  );
}
