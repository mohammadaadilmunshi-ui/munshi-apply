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

export const FillInstructionSchema = z.object({
  controlId: z.string().min(1),
  frameId: z.number().int().nonnegative(),
  value: z.string(),
  sensitive: z.boolean(),
  approved: z.boolean(),
  sourceDraftId: z.string().min(1).optional(),
});
export type FillInstruction = z.infer<typeof FillInstructionSchema>;

export const FillPlanSchema = z.object({
  pageId: z.string().min(1),
  instructions: z.array(FillInstructionSchema),
});
export type FillPlan = z.infer<typeof FillPlanSchema>;

export type FillResult = {
  controlId: string;
  status: "FILLED" | "SKIPPED" | "FAILED";
  reason: string;
  strategy?: string;
  verification?: string;
  rebound?: boolean;
  stabilized?: boolean;
  componentFingerprint?: string;
  recipeId?: string;
  recipeAttempted?: boolean;
  recipeSucceeded?: boolean;
};

export const semanticTypes = [
  "PERSONAL",
  "FIRST_NAME",
  "MIDDLE_NAME",
  "LAST_NAME",
  "PREFERRED_NAME",
  "HONORIFIC",
  "PRONOUNS",
  "CONTACT",
  "ADDRESS",
  "CURRENT_LOCATION",
  "STREET_ADDRESS",
  "ADDRESS_LINE_2",
  "CITY",
  "STATE_PROVINCE",
  "POSTAL_CODE",
  "COUNTRY",
  "EMAIL",
  "PHONE",
  "LINKEDIN",
  "GITHUB",
  "PORTFOLIO",
  "WEBSITE",
  "EDUCATION",
  "SCHOOL_NAME",
  "DEGREE",
  "FIELD_OF_STUDY",
  "EDUCATION_LOCATION",
  "EDUCATION_START_DATE",
  "GRADUATION_DATE",
  "GPA",
  "EMPLOYMENT",
  "EMPLOYER_NAME",
  "JOB_TITLE",
  "EMPLOYMENT_LOCATION",
  "EMPLOYMENT_START_DATE",
  "EMPLOYMENT_END_DATE",
  "EMPLOYMENT_DATES",
  "EMPLOYMENT_TYPE",
  "CURRENTLY_EMPLOYED",
  "COMPANY_INDUSTRY",
  "POSITION_FUNCTION",
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
  "CERTIFICATION_ISSUER",
  "CERTIFICATION_ISSUE_DATE",
  "CERTIFICATION_EXPIRATION_DATE",
  "CREDENTIAL_ID",
  "CREDENTIAL_URL",
  "LANGUAGES",
  "LANGUAGE_PROFICIENCY",
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

export const securityCheckpointKinds = [
  "CAPTCHA",
  "MFA",
  "OTP",
  "IDENTITY_VERIFICATION",
  "AUTHENTICATION",
] as const;
export const SecurityCheckpointKindSchema = z.enum(securityCheckpointKinds);
export type SecurityCheckpointKind = z.infer<
  typeof SecurityCheckpointKindSchema
>;

export const navigationActions = [
  "NEXT",
  "BACK",
  "REVIEW",
  "FINAL_SUBMIT",
] as const;
export const NavigationActionSchema = z.enum(navigationActions);
export type NavigationAction = z.infer<typeof NavigationActionSchema>;

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
  multiple: z.boolean().default(false),
  autocomplete: z.string().default(""),
  invalid: z.boolean().default(false),
  validationMessage: z.string().default(""),
  fileSelected: z.boolean().optional(),
  role: z.string().optional(),
  inputType: z.string().optional(),
  hasPopup: z.string().optional(),
  readOnly: z.boolean().optional(),
  maxLength: z.number().int().optional(),
  minLength: z.number().int().optional(),
  pattern: z.string().optional(),
  accept: z.string().optional(),
  satisfied: z.boolean().optional(),
  validationCode: z
    .enum([
      "NONE",
      "REQUIRED",
      "FORMAT",
      "TOO_LONG",
      "TOO_SHORT",
      "RANGE",
      "PATTERN",
      "FILE_TYPE",
      "FILE_SIZE",
      "UNKNOWN",
    ])
    .optional(),
  interactionConfidence: z.number().min(0).max(1).optional(),
  repeatGroupId: z.string().nullable().optional(),
  repeatIndex: z.number().int().nonnegative().nullable().optional(),
  componentFingerprint: z.string().optional(),
  fileFingerprintState: z
    .enum(["NONE", "PENDING", "READY", "ERROR"])
    .optional(),
  fileSha256: z
    .string()
    .regex(/^[a-f0-9]{64}$/)
    .nullable()
    .optional(),
  fileCount: z.number().int().nonnegative().optional(),
  fileSize: z.number().int().nonnegative().nullable().optional(),
  fileMimeType: z.string().nullable().optional(),
});
export type Control = z.infer<typeof ControlSchema>;

export const QuestionSchema = z.object({
  questionId: z.string().min(1),
  controlId: z.string().min(1),
  rawText: z.string(),
  contextText: z.string().optional(),
  semanticType: SemanticTypeSchema,
  confidence: z.number().min(0).max(1),
  sensitive: z.boolean(),
  requiresReview: z.boolean(),
  repeatGroupId: z.string().nullable().optional(),
  repeatIndex: z.number().int().nonnegative().nullable().optional(),
});
export type Question = z.infer<typeof QuestionSchema>;

export const NavigationCandidateSchema = z.object({
  controlId: z.string().min(1),
  frameId: z.number().int().nonnegative(),
  action: NavigationActionSchema,
  label: z.string(),
  disabled: z.boolean(),
});
export type NavigationCandidate = z.infer<typeof NavigationCandidateSchema>;

export const ApplicationPageSchema = z.object({
  pageId: z.string().min(1),
  tabId: z.number().int(),
  frameId: z.number().int().nonnegative(),
  documentId: z.string().min(1),
  url: z.string().url(),
  title: z.string(),
  pageContext: z.string().max(20_000).optional(),
  observedAt: z.string().datetime(),
  controls: z.array(ControlSchema),
  questions: z.array(QuestionSchema),
  applicationState: ApplicationStateSchema.default("QUESTIONS"),
  pageFingerprint: z.string().default(""),
  securityCheckpoint: SecurityCheckpointKindSchema.nullable().default(null),
  validationErrorCount: z.number().int().nonnegative().default(0),
  navigationCandidates: z.array(NavigationCandidateSchema).default([]),
  finalSubmissionBoundary: z.boolean().default(false),
  atsFamily: z
    .enum([
      "WORKDAY",
      "GREENHOUSE",
      "LEVER",
      "ASHBY",
      "SMARTRECRUITERS",
      "ICIMS",
      "TALEO",
      "GENERIC",
    ])
    .optional(),
});
export type ApplicationPage = z.infer<typeof ApplicationPageSchema>;

export const eventTypes = [
  "PAGE_DETECTED",
  "APPLICATION_DETECTED",
  "APPLICATION_PREPARED",
  "AUTOPILOT_STARTED",
  "FIELD_DISCOVERED",
  "QUESTION_CLASSIFIED",
  "ANSWER_RESOLVED",
  "ANSWER_REVIEW_REQUIRED",
  "QUESTION_REVIEW_REQUIRED",
  "RESUME_SELECTED",
  "RESUME_UPLOADED",
  "RESUME_VERIFIED",
  "UPLOAD_VERIFIED",
  "ACCOUNT_REQUIRED",
  "ACCOUNT_CREATED",
  "APPLICATION_STATE_CHANGED",
  "CHECKPOINT_REQUIRED",
  "SECURITY_CHECKPOINT",
  "INTERACTION_FAILED",
  "RECOVERY_SUCCEEDED",
  "APPLICATION_READY",
  "APPLICATION_SUBMITTED",
  "APPLICATION_CONFIRMED",
  "APPLICATION_COMPLETED",
  "PORTFOLIO_VISIT_OBSERVED",
  "FOLLOWUP_DUE",
  "ASSESSMENT_RECEIVED",
  "INTERVIEW_RECEIVED",
  "REJECTION_RECEIVED",
  "OFFER_RECEIVED",
  "STATUS_CHANGED",
  "LEARNING_EVENT_CREATED",
] as const;
export const EventTypeSchema = z.enum(eventTypes);
export type EventType = z.infer<typeof EventTypeSchema>;

export const EventEnvelopeSchema = z.object({
  schema_version: z.literal("1.0"),
  event_id: z.string().min(1).max(128),
  correlation_id: z.string().min(1).max(128),
  event_type: EventTypeSchema,
  occurred_at: z.string().datetime({ offset: true }),
  application_id: z.string().nullable(),
  source: z.literal("munshi-apply"),
  payload: z.record(z.string(), z.unknown()),
});
export type EventEnvelope = z.infer<typeof EventEnvelopeSchema>;

export type ExtensionRequest =
  | { type: "GET_ACTIVE_PAGE" }
  | { type: "GET_PROFILE" }
  | { type: "GET_PROFILE_SYNC_STATUS" }
  | {
      type: "RESOLVE_PROFILE_SYNC_CONFLICT";
      payload: { winner: "local" | "remote" };
    }
  | { type: "SAVE_PROFILE"; payload: MasterProfile }
  | { type: "APPLY_FILL_PLAN"; payload: FillPlan }
  | { type: "PAGE_SNAPSHOT"; payload: ApplicationPage }
  | { type: "NATIVE_HEALTH" }
  | { type: "PING" };

export type ExtensionResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };
