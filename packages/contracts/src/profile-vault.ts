import { z } from "zod";
import { ProfileFactSchema } from "./index";

export const profileRecordKinds = [
  "EDUCATION",
  "EMPLOYMENT",
  "PROJECT",
  "CERTIFICATION",
  "LANGUAGE",
] as const;

export const ProfileRecordKindSchema = z.enum(profileRecordKinds);
export type ProfileRecordKind = z.infer<typeof ProfileRecordKindSchema>;

export const ProfileRecordSchema = z.object({
  recordId: z.string().min(1),
  kind: ProfileRecordKindSchema,
  label: z.string().min(1),
  facts: z.array(ProfileFactSchema),
  sortOrder: z.number().int().nonnegative().default(0),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});
export type ProfileRecord = z.infer<typeof ProfileRecordSchema>;

export const ProfileRecordTombstoneSchema = z.object({
  recordId: z.string().min(1),
  kind: ProfileRecordKindSchema,
  deletedAt: z.string().datetime(),
  confirmed: z.literal(true),
});
export type ProfileRecordTombstone = z.infer<
  typeof ProfileRecordTombstoneSchema
>;

/**
 * Canonical cross-device profile payload.
 *
 * The MasterProfile fields stay at the top level so every V1 flat-profile
 * consumer can continue to read the payload. Snapshot-specific fields are
 * additive and receive safe defaults when a legacy flat profile is parsed.
 */
export const ProfileSnapshotSchema = z
  .object({
    profileId: z.string().min(1),
    displayName: z.string().min(1),
    facts: z.array(ProfileFactSchema),
    records: z.array(ProfileRecordSchema).default([]),
    recordTombstones: z.array(ProfileRecordTombstoneSchema).default([]),
    createdAt: z.string().datetime(),
    updatedAt: z.string().datetime(),
    schemaVersion: z.literal(1),
    snapshotVersion: z.literal(1).default(1),
  })
  .superRefine((snapshot, context) => {
    const recordIds = new Set<string>();
    const factIds = new Set(snapshot.facts.map((fact) => fact.factId));

    for (const record of snapshot.records) {
      if (recordIds.has(record.recordId)) {
        context.addIssue({
          code: "custom",
          message: `Duplicate profile record id: ${record.recordId}`,
          path: ["records"],
        });
      }
      recordIds.add(record.recordId);

      const keys = new Set<string>();
      for (const fact of record.facts) {
        if (keys.has(fact.key)) {
          context.addIssue({
            code: "custom",
            message: `Duplicate fact key in ${record.recordId}: ${fact.key}`,
            path: ["records"],
          });
        }
        keys.add(fact.key);
        if (factIds.has(fact.factId)) {
          context.addIssue({
            code: "custom",
            message: `Duplicate profile fact id: ${fact.factId}`,
            path: ["records"],
          });
        }
        factIds.add(fact.factId);
      }
    }

    const tombstoneIds = new Set<string>();
    for (const tombstone of snapshot.recordTombstones) {
      if (tombstoneIds.has(tombstone.recordId)) {
        context.addIssue({
          code: "custom",
          message: `Duplicate profile tombstone id: ${tombstone.recordId}`,
          path: ["recordTombstones"],
        });
      }
      tombstoneIds.add(tombstone.recordId);
      if (recordIds.has(tombstone.recordId)) {
        context.addIssue({
          code: "custom",
          message: `Record and tombstone overlap: ${tombstone.recordId}`,
          path: ["recordTombstones"],
        });
      }
    }
  });
export type ProfileSnapshot = z.infer<typeof ProfileSnapshotSchema>;

export function parseProfileSnapshot(value: unknown): ProfileSnapshot {
  return ProfileSnapshotSchema.parse(value);
}

export const resumeSources = ["MASTER", "TAILORED", "IMPORTED"] as const;
export const ResumeSourceSchema = z.enum(resumeSources);
export type ResumeSource = z.infer<typeof ResumeSourceSchema>;

export const ResumeVersionSchema = z.object({
  resumeId: z.string().min(1),
  family: z.string().min(1),
  version: z.number().int().positive(),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  filename: z.string().min(1),
  contentType: z.string().min(1),
  sizeBytes: z.number().int().positive(),
  source: ResumeSourceSchema,
  roleFamily: z.string().min(1).nullable(),
  active: z.boolean(),
  createdAt: z.string().datetime(),
});
export type ResumeVersion = z.infer<typeof ResumeVersionSchema>;

export const ApplicationResumeSelectionSchema = z.object({
  applicationId: z.string().min(1),
  resumeId: z.string().min(1),
  resumeSha256: z.string().regex(/^[a-f0-9]{64}$/),
  lockedAt: z.string().datetime(),
});
export type ApplicationResumeSelection = z.infer<
  typeof ApplicationResumeSelectionSchema
>;
