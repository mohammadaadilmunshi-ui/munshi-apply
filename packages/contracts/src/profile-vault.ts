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
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});
export type ProfileRecord = z.infer<typeof ProfileRecordSchema>;

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
