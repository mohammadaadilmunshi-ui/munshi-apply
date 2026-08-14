import { z } from "zod";

export const trustLevels = [
  "VERIFIED",
  "USER_CONFIRMED",
  "DOCUMENT_CONFIRMED",
  "DERIVED",
  "GENERATED",
  "LEARNED",
  "UNKNOWN",
] as const;

export const TrustLevelSchema = z.enum(trustLevels);
export type TrustLevel = z.infer<typeof TrustLevelSchema>;

export const factCategories = [
  "IDENTITY",
  "CONTACT",
  "ADDRESS",
  "EDUCATION",
  "EMPLOYMENT",
  "PROJECT",
  "SKILL",
  "CERTIFICATION",
  "LANGUAGE",
  "AVAILABILITY",
  "WORK_PREFERENCE",
  "WORK_AUTHORIZATION",
  "SPONSORSHIP",
  "VOLUNTARY_DEMOGRAPHIC",
  "SAVED_ANSWER",
  "WRITING_PREFERENCE",
] as const;

export const FactCategorySchema = z.enum(factCategories);
export type FactCategory = z.infer<typeof FactCategorySchema>;

export const ProfileFactSchema = z.object({
  factId: z.string().min(1),
  key: z.string().min(1),
  value: z.union([z.string(), z.number(), z.boolean(), z.array(z.string())]),
  category: FactCategorySchema,
  trustLevel: TrustLevelSchema,
  source: z.string().min(1),
  confirmedAt: z.string().datetime().nullable(),
  updatedAt: z.string().datetime(),
  protected: z.boolean(),
});
export type ProfileFact = z.infer<typeof ProfileFactSchema>;

export const MasterProfileSchema = z.object({
  profileId: z.string().min(1),
  displayName: z.string().min(1),
  facts: z.array(ProfileFactSchema),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  schemaVersion: z.literal(1),
});
export type MasterProfile = z.infer<typeof MasterProfileSchema>;

export const semanticTypes = [
  "PERSONAL",
  "CONTACT",
  "ADDRESS",
  "EMAIL",
  "PHONE",
  "LINKEDIN",
  "PORTFOLIO",
  "WEBSITE",
  "EDUCATION",
  "DEGREE",
  "FIELD_OF_STUDY",
  "GRADUATION_DATE",
  "GPA",
  "EMPLOYMENT",
  "EMPLOYMENT_DATES",
  "EMPLOYMENT_RESPONSIBILITIES",
  "WORK_AUTHORIZATION_CURRENT",
  "SPONSORSHIP_CURRENT",
  "SPONSORSHIP_FUTURE",
  "IMMIGRATION_ASSISTANCE",
  "SALARY_EXPECTATION",
  "START_DATE",
  "NOTICE_PERIOD",
  "RELOCATION",
  "TRAVEL",
  "REMOTE",
  "HYBRID",
  "ONSITE",
  "SKILLS",
  "CERTIFICATIONS",
  "LICENSES",
  "LANGUAGES",
  "SECURITY_CLEARANCE",
  "VETERAN_STATUS",
  "PROTECTED_VETERAN_STATUS",
  "DISABILITY_STATUS",
  "GENDER",
  "RACE_ETHNICITY",
  "EEO_SELF_ID",
  "REFERRAL",
  "PREVIOUS_EMPLOYEE",
  "PREVIOUS_APPLICATION",
  "CONFLICT_OF_INTEREST",
  "NON_COMPETE",
  "BACKGROUND_CHECK",
  "DRUG_SCREENING",
  "WHY_COMPANY",
  "WHY_ROLE",
  "RELEVANT_EXPERIENCE",
  "CAREER_GOALS",
  "BEHAVIORAL_EXAMPLE",
  "UNKNOWN",
] as const;

export const SemanticTypeSchema = z.enum(semanticTypes);
export type SemanticType = z.infer<typeof SemanticTypeSchema>;

export const controlKinds = [
  "TEXT",
  "EMAIL",
  "TEL",
  "NUMBER",
  "DATE",
  "TEXTAREA",
  "SELECT",
  "CHECKBOX",
  "RADIO",
  "FILE",
  "BUTTON",
  "COMBOBOX",
  "UNKNOWN",
] as const;

export const ControlKindSchema = z.enum(controlKinds);
export type ControlKind = z.infer<typeof ControlKindSchema>;

export const ControlSchema = z.object({
  controlId: z.string().min(1),
  frameId: z.number().int().nonnegative(),
  kind: ControlKindSchema,
  tagName: z.string().min(1),
  name: z.string(),
  label: z.string(),
  placeholder: z.string(),
  ariaLabel: z.string(),
  required: z.boolean(),
  disabled: z.boolean(),
  visible: z.boolean(),
  options: z.array(z.string()),
});
export type Control = z.infer<typeof ControlSchema>;

export const QuestionSchema = z.object({
  questionId: z.string().min(1),
  controlId: z.string().min(1),
  rawText: z.string(),
  semanticType: SemanticTypeSchema,
  confidence: z.number().min(0).max(1),
  sensitive: z.boolean(),
  requiresReview: z.boolean(),
});
export type Question = z.infer<typeof QuestionSchema>;

export const ApplicationPageSchema = z.object({
  pageId: z.string().min(1),
  tabId: z.number().int(),
  frameId: z.number().int().nonnegative(),
  documentId: z.string().min(1),
  url: z.string().url(),
  title: z.string(),
  observedAt: z.string().datetime(),
  controls: z.array(ControlSchema),
  questions: z.array(QuestionSchema),
});
export type ApplicationPage = z.infer<typeof ApplicationPageSchema>;

export const applicationStates = [
  "JOB_CONTEXT",
  "AUTH",
  "ACCOUNT_CREATE",
  "VERIFY_ACCOUNT",
  "PERSONAL",
  "EDUCATION",
  "EXPERIENCE",
  "RESUME",
  "QUESTIONS",
  "EEO",
  "DISCLOSURES",
  "REVIEW",
  "SUBMISSION",
  "CONFIRMATION",
  "COMPLETE",
] as const;
export const ApplicationStateSchema = z.enum(applicationStates);
export type ApplicationState = z.infer<typeof ApplicationStateSchema>;

export const eventTypes = [
  "PAGE_DETECTED",
  "APPLICATION_DETECTED",
  "FIELD_DISCOVERED",
  "QUESTION_CLASSIFIED",
  "ANSWER_RESOLVED",
  "ANSWER_REVIEW_REQUIRED",
  "RESUME_SELECTED",
  "RESUME_UPLOADED",
  "UPLOAD_VERIFIED",
  "ACCOUNT_REQUIRED",
  "ACCOUNT_CREATED",
  "APPLICATION_STATE_CHANGED",
  "CHECKPOINT_REQUIRED",
  "INTERACTION_FAILED",
  "RECOVERY_SUCCEEDED",
  "APPLICATION_READY",
  "APPLICATION_SUBMITTED",
  "APPLICATION_COMPLETED",
  "LEARNING_EVENT_CREATED",
] as const;
export const EventTypeSchema = z.enum(eventTypes);
export type EventType = z.infer<typeof EventTypeSchema>;

export const EventEnvelopeSchema = z.object({
  eventId: z.string().min(1),
  eventType: EventTypeSchema,
  occurredAt: z.string().datetime(),
  source: z.enum(["EXTENSION", "NATIVE_HOST", "USER", "N8N"]),
  applicationId: z.string().nullable(),
  payload: z.record(z.string(), z.unknown()),
  schemaVersion: z.literal(1),
});
export type EventEnvelope = z.infer<typeof EventEnvelopeSchema>;

export type ExtensionRequest =
  | { type: "GET_ACTIVE_PAGE" }
  | { type: "GET_PROFILE" }
  | { type: "SAVE_PROFILE"; payload: MasterProfile }
  | { type: "PAGE_SNAPSHOT"; payload: ApplicationPage }
  | { type: "PING" };

export type ExtensionResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };
