import type { SemanticType } from "@munshi-apply/contracts";
import type {
  EmployerPreflightFinding,
  EmployerRequirementKind,
} from "./employer-preflight";

export const RESOLUTION_TASK_SCHEMA_VERSION = 1 as const;

export const resolutionTaskCategories = [
  "MISSING_FACT",
  "AMBIGUOUS_QUESTION",
  "LOW_CONFIDENCE",
  "AUTHENTICATION",
  "EMAIL_VERIFICATION",
  "INTERACTION_FAILURE",
  "DOCUMENT_REQUIRED",
  "LEGAL_CONFIRMATION",
  "CAPTCHA",
  "EXTERNAL_ACTION",
  "TEMPORARY_FAILURE",
  "BLOCKING_CONFLICT",
] as const;
export type ResolutionTaskCategory = (typeof resolutionTaskCategories)[number];

export const resolutionTaskStatuses = [
  "PENDING",
  "RESOLVING",
  "WAITING_FOR_USER",
  "RESOLVED",
  "FAILED",
  "EXPIRED",
] as const;
export type ResolutionTaskStatus = (typeof resolutionTaskStatuses)[number];

export const resolutionRiskLevels = ["LOW", "MEDIUM", "HIGH"] as const;
export type ResolutionRiskLevel = (typeof resolutionRiskLevels)[number];

export const resolverStages = [
  "CURRENT_SESSION",
  "MASTER_PROFILE",
  "EVIDENCE_GRAPH",
  "APPROVED_ANSWER_MEMORY",
  "SCOPED_MEMORY",
  "DETERMINISTIC_DERIVATION",
  "GROUNDED_AI",
  "EXTERNAL_RESOLVER",
  "USER_POLICY",
  "USER",
] as const;
export type ResolverStage = (typeof resolverStages)[number];

export type ResolutionGroupingScope = "NONE" | "EXACT_QUESTION" | "SEMANTIC";

export type ResolutionTaskResolution = {
  value: unknown;
  source: ResolverStage;
  evidenceRefs: readonly string[];
  approvedByUser: boolean;
  resolvedAt: string;
};

export type ResolutionTask = {
  schemaVersion: typeof RESOLUTION_TASK_SCHEMA_VERSION;
  taskId: string;
  applicationId: string;
  sessionId: string | null;
  checkpointId: string | null;
  pageId: string | null;
  controlId: string | null;
  questionId: string | null;
  question: string | null;
  semanticType: SemanticType | null;
  category: ResolutionTaskCategory;
  status: ResolutionTaskStatus;
  riskLevel: ResolutionRiskLevel;
  autoResolvable: boolean;
  requiresUser: boolean;
  groupingScope: ResolutionGroupingScope;
  groupKey: string | null;
  sourceRefs: readonly string[];
  evidenceRefs: readonly string[];
  attemptedResolvers: readonly ResolverStage[];
  reason: string;
  resolution: ResolutionTaskResolution | null;
  createdAt: string;
  updatedAt: string;
};

export type ResolutionPolicy = {
  riskLevel: ResolutionRiskLevel;
  resolverStages: readonly ResolverStage[];
  requiresUser: boolean;
  allowAutomaticResolution: boolean;
};

const highRiskSemanticTypes = new Set<SemanticType>([
  "WORK_AUTHORIZATION_CURRENT",
  "SPONSORSHIP_CURRENT",
  "SPONSORSHIP_FUTURE",
  "IMMIGRATION_ASSISTANCE",
  "SECURITY_CLEARANCE",
  "VETERAN_STATUS",
  "PROTECTED_VETERAN_STATUS",
  "DISABILITY_STATUS",
  "GENDER",
  "RACE_ETHNICITY",
  "EEO_SELF_ID",
  "CONFLICT_OF_INTEREST",
  "NON_COMPETE",
  "BACKGROUND_CHECK",
  "DRUG_SCREENING",
]);

const demographicSemanticTypes = new Set<SemanticType>([
  "VETERAN_STATUS",
  "PROTECTED_VETERAN_STATUS",
  "DISABILITY_STATUS",
  "GENDER",
  "RACE_ETHNICITY",
  "EEO_SELF_ID",
]);

const semanticGroupingTypes = new Set<SemanticType>([
  "FIRST_NAME",
  "MIDDLE_NAME",
  "LAST_NAME",
  "PREFERRED_NAME",
  "PRONOUNS",
  "EMAIL",
  "PHONE",
  "LINKEDIN",
  "GITHUB",
  "PORTFOLIO",
  "WEBSITE",
  "STREET_ADDRESS",
  "ADDRESS_LINE_2",
  "CITY",
  "STATE_PROVINCE",
  "POSTAL_CODE",
  "COUNTRY",
  "WORK_AUTHORIZATION_CURRENT",
  "SPONSORSHIP_CURRENT",
  "SPONSORSHIP_FUTURE",
  "IMMIGRATION_ASSISTANCE",
  "NOTICE_PERIOD",
  "RELOCATION",
  "TRAVEL",
  "REMOTE",
  "HYBRID",
  "ONSITE",
  "SECURITY_CLEARANCE",
]);

const contextSpecificSemanticTypes = new Set<SemanticType>([
  "WHY_COMPANY",
  "WHY_ROLE",
  "RELEVANT_EXPERIENCE",
  "CAREER_GOALS",
  "BEHAVIORAL_EXAMPLE",
]);

const legalRequirementKinds = new Set<EmployerRequirementKind>([
  "WORK_AUTHORIZATION",
  "SPONSORSHIP",
  "CITIZENSHIP",
  "SECURITY_CLEARANCE",
]);

function requiredString(value: string, name: string): string {
  const result = value.trim();
  if (!result) throw new Error(`${name} must be a non-empty string`);
  return result;
}

function nullableString(value: string | null | undefined): string | null {
  const result = value?.trim() ?? "";
  return result || null;
}

function assertTimestamp(value: string, name: string): string {
  const result = requiredString(value, name);
  if (Number.isNaN(Date.parse(result))) {
    throw new Error(`${name} must be an ISO-compatible timestamp`);
  }
  return result;
}

function compact(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function normalizedQuestion(value: string): string {
  return compact(value)
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[’‘]/g, "'")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function stableHash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function uniqueStrings(values: readonly string[]): string[] {
  return Array.from(
    new Set(values.map((value) => value.trim()).filter(Boolean)),
  );
}

function isHighRiskSemanticType(
  semanticType: SemanticType | null | undefined,
): boolean {
  return semanticType ? highRiskSemanticTypes.has(semanticType) : false;
}

function groupingFor(input: {
  category: ResolutionTaskCategory;
  semanticType?: SemanticType | null;
  question?: string | null;
}): { scope: ResolutionGroupingScope; key: string | null } {
  if (
    [
      "AUTHENTICATION",
      "EMAIL_VERIFICATION",
      "INTERACTION_FAILURE",
      "CAPTCHA",
      "EXTERNAL_ACTION",
      "TEMPORARY_FAILURE",
      "BLOCKING_CONFLICT",
    ].includes(input.category)
  ) {
    return { scope: "NONE", key: null };
  }

  const semanticType = input.semanticType ?? null;
  if (
    semanticType &&
    semanticGroupingTypes.has(semanticType) &&
    !demographicSemanticTypes.has(semanticType) &&
    !contextSpecificSemanticTypes.has(semanticType)
  ) {
    return { scope: "SEMANTIC", key: `semantic:${semanticType}` };
  }

  const question = normalizedQuestion(input.question ?? "");
  if (question) {
    return { scope: "EXACT_QUESTION", key: `question:${question}` };
  }
  return { scope: "NONE", key: null };
}

export function resolutionPolicy(input: {
  category: ResolutionTaskCategory;
  semanticType?: SemanticType | null;
}): ResolutionPolicy {
  const highRisk = isHighRiskSemanticType(input.semanticType);

  if (input.category === "CAPTCHA") {
    return {
      riskLevel: "HIGH",
      resolverStages: ["USER"],
      requiresUser: true,
      allowAutomaticResolution: false,
    };
  }

  if (
    input.category === "LEGAL_CONFIRMATION" ||
    input.category === "BLOCKING_CONFLICT"
  ) {
    return {
      riskLevel: "HIGH",
      resolverStages: [
        "MASTER_PROFILE",
        "EVIDENCE_GRAPH",
        "APPROVED_ANSWER_MEMORY",
        "USER_POLICY",
        "USER",
      ],
      requiresUser: true,
      allowAutomaticResolution: false,
    };
  }

  if (input.category === "AUTHENTICATION") {
    return {
      riskLevel: "HIGH",
      resolverStages: ["EXTERNAL_RESOLVER", "USER"],
      requiresUser: false,
      allowAutomaticResolution: true,
    };
  }

  if (input.category === "EMAIL_VERIFICATION") {
    return {
      riskLevel: "MEDIUM",
      resolverStages: ["EXTERNAL_RESOLVER", "USER"],
      requiresUser: false,
      allowAutomaticResolution: true,
    };
  }

  if (input.category === "INTERACTION_FAILURE") {
    return {
      riskLevel: "MEDIUM",
      resolverStages: [
        "SCOPED_MEMORY",
        "DETERMINISTIC_DERIVATION",
        "EXTERNAL_RESOLVER",
        "USER",
      ],
      requiresUser: false,
      allowAutomaticResolution: true,
    };
  }

  if (input.category === "DOCUMENT_REQUIRED") {
    return {
      riskLevel: "MEDIUM",
      resolverStages: [
        "CURRENT_SESSION",
        "MASTER_PROFILE",
        "EVIDENCE_GRAPH",
        "EXTERNAL_RESOLVER",
        "USER",
      ],
      requiresUser: false,
      allowAutomaticResolution: true,
    };
  }

  if (input.category === "TEMPORARY_FAILURE") {
    return {
      riskLevel: "LOW",
      resolverStages: ["CURRENT_SESSION", "EXTERNAL_RESOLVER", "USER"],
      requiresUser: false,
      allowAutomaticResolution: true,
    };
  }

  if (highRisk) {
    return {
      riskLevel: "HIGH",
      resolverStages: [
        "CURRENT_SESSION",
        "MASTER_PROFILE",
        "EVIDENCE_GRAPH",
        "APPROVED_ANSWER_MEMORY",
        "USER_POLICY",
        "USER",
      ],
      requiresUser: false,
      allowAutomaticResolution: true,
    };
  }

  return {
    riskLevel:
      input.category === "LOW_CONFIDENCE" ||
      input.category === "AMBIGUOUS_QUESTION"
        ? "MEDIUM"
        : "LOW",
    resolverStages: [
      "CURRENT_SESSION",
      "MASTER_PROFILE",
      "EVIDENCE_GRAPH",
      "APPROVED_ANSWER_MEMORY",
      "SCOPED_MEMORY",
      "DETERMINISTIC_DERIVATION",
      "GROUNDED_AI",
      "EXTERNAL_RESOLVER",
      "USER_POLICY",
      "USER",
    ],
    requiresUser: false,
    allowAutomaticResolution: true,
  };
}

export function createResolutionTask(input: {
  taskId?: string;
  applicationId: string;
  sessionId?: string | null;
  checkpointId?: string | null;
  pageId?: string | null;
  controlId?: string | null;
  questionId?: string | null;
  question?: string | null;
  semanticType?: SemanticType | null;
  category: ResolutionTaskCategory;
  reason: string;
  sourceRefs?: readonly string[];
  evidenceRefs?: readonly string[];
  createdAt: string;
}): ResolutionTask {
  const applicationId = requiredString(input.applicationId, "applicationId");
  const reason = requiredString(input.reason, "reason");
  const createdAt = assertTimestamp(input.createdAt, "createdAt");
  const grouping = groupingFor(input);
  const policy = resolutionPolicy(input);
  const identity = [
    applicationId,
    input.sessionId ?? "",
    input.checkpointId ?? "",
    input.pageId ?? "",
    input.controlId ?? "",
    input.questionId ?? "",
    input.category,
    input.semanticType ?? "",
    grouping.key ?? "",
    reason,
  ].join("|");

  return {
    schemaVersion: RESOLUTION_TASK_SCHEMA_VERSION,
    taskId: input.taskId?.trim() || `resolution-${stableHash(identity)}`,
    applicationId,
    sessionId: nullableString(input.sessionId),
    checkpointId: nullableString(input.checkpointId),
    pageId: nullableString(input.pageId),
    controlId: nullableString(input.controlId),
    questionId: nullableString(input.questionId),
    question: nullableString(input.question),
    semanticType: input.semanticType ?? null,
    category: input.category,
    status: "PENDING",
    riskLevel: policy.riskLevel,
    autoResolvable: policy.allowAutomaticResolution,
    requiresUser: policy.requiresUser,
    groupingScope: grouping.scope,
    groupKey: grouping.key,
    sourceRefs: uniqueStrings(input.sourceRefs ?? []),
    evidenceRefs: uniqueStrings(input.evidenceRefs ?? []),
    attemptedResolvers: [],
    reason,
    resolution: null,
    createdAt,
    updatedAt: createdAt,
  };
}

function preflightCategory(
  finding: EmployerPreflightFinding,
): ResolutionTaskCategory {
  if (finding.state === "BLOCKED") return "BLOCKING_CONFLICT";
  if (legalRequirementKinds.has(finding.requirement.kind)) {
    return finding.state === "REVIEW" ? "LEGAL_CONFIRMATION" : "MISSING_FACT";
  }
  if (finding.candidateValue === null) return "MISSING_FACT";
  return "LOW_CONFIDENCE";
}

/**
 * Converts an actionable preflight finding into the same durable task model
 * that interactive side-panel UX and future unattended AutoApply orchestration
 * can consume. READY findings intentionally produce no task.
 */
export function resolutionTaskFromPreflightFinding(input: {
  finding: EmployerPreflightFinding;
  applicationId: string;
  sessionId?: string | null;
  checkpointId?: string | null;
  pageId?: string | null;
  createdAt: string;
}): ResolutionTask | null {
  if (input.finding.state === "READY") return null;
  const requirement = input.finding.requirement;
  return createResolutionTask({
    applicationId: input.applicationId,
    sessionId: input.sessionId,
    checkpointId: input.checkpointId,
    pageId: input.pageId,
    question: requirement.sourceText,
    semanticType: requirement.semanticType,
    category: preflightCategory(input.finding),
    reason: input.finding.reason,
    sourceRefs: [requirement.requirementId],
    createdAt: input.createdAt,
  });
}

function assertTaskOpen(task: ResolutionTask): void {
  if (["RESOLVED", "FAILED", "EXPIRED"].includes(task.status)) {
    throw new Error(`Resolution task ${task.taskId} is already terminal`);
  }
}

function updated(task: ResolutionTask, at: string): ResolutionTask {
  const updatedAt = assertTimestamp(at, "updatedAt");
  if (Date.parse(updatedAt) < Date.parse(task.updatedAt)) {
    throw new Error("Resolution task updates must be monotonic");
  }
  return { ...task, updatedAt };
}

export function recordResolutionAttempt(
  task: ResolutionTask,
  stage: ResolverStage,
  at: string,
): ResolutionTask {
  assertTaskOpen(task);
  const policy = resolutionPolicy(task);
  if (!policy.resolverStages.includes(stage)) {
    throw new Error(
      `Resolver stage ${stage} is not permitted for ${task.category}`,
    );
  }
  return {
    ...updated(task, at),
    status: "RESOLVING",
    attemptedResolvers: uniqueStrings([
      ...task.attemptedResolvers,
      stage,
    ]) as ResolverStage[],
  };
}

export function waitForResolutionUser(
  task: ResolutionTask,
  at: string,
): ResolutionTask {
  assertTaskOpen(task);
  return {
    ...updated(task, at),
    status: "WAITING_FOR_USER",
    requiresUser: true,
  };
}

export function resolveResolutionTask(
  task: ResolutionTask,
  input: {
    value: unknown;
    source: ResolverStage;
    evidenceRefs?: readonly string[];
    approvedByUser?: boolean;
    resolvedAt: string;
  },
): ResolutionTask {
  assertTaskOpen(task);
  const policy = resolutionPolicy(task);
  if (!policy.resolverStages.includes(input.source)) {
    throw new Error(
      `Resolver stage ${input.source} is not permitted for ${task.category}`,
    );
  }
  if (
    !policy.allowAutomaticResolution &&
    input.source !== "USER" &&
    !input.approvedByUser
  ) {
    throw new Error(`${task.category} requires explicit user approval`);
  }
  if (task.riskLevel === "HIGH" && input.source === "GROUNDED_AI") {
    throw new Error("High-risk resolution tasks cannot be resolved by AI");
  }
  const resolvedAt = assertTimestamp(input.resolvedAt, "resolvedAt");
  return {
    ...updated(task, resolvedAt),
    status: "RESOLVED",
    requiresUser: false,
    evidenceRefs: uniqueStrings([
      ...task.evidenceRefs,
      ...(input.evidenceRefs ?? []),
    ]),
    attemptedResolvers: uniqueStrings([
      ...task.attemptedResolvers,
      input.source,
    ]) as ResolverStage[],
    resolution: {
      value: input.value,
      source: input.source,
      evidenceRefs: uniqueStrings(input.evidenceRefs ?? []),
      approvedByUser: Boolean(input.approvedByUser),
      resolvedAt,
    },
  };
}

export function failResolutionTask(
  task: ResolutionTask,
  input: { reason: string; at: string; expired?: boolean },
): ResolutionTask {
  assertTaskOpen(task);
  return {
    ...updated(task, input.at),
    status: input.expired ? "EXPIRED" : "FAILED",
    reason: requiredString(input.reason, "reason"),
  };
}

export type ResolutionTaskGroup = {
  groupKey: string;
  semanticType: SemanticType | null;
  question: string | null;
  applicationIds: readonly string[];
  taskIds: readonly string[];
  tasks: readonly ResolutionTask[];
};

/**
 * Groups only tasks whose canonical grouping key is deliberately reusable.
 * Tasks with NONE scope stay independent, which prevents login/CAPTCHA/site
 * failures from being accidentally treated as one reusable user answer.
 */
export function groupResolutionTasks(
  tasks: readonly ResolutionTask[],
): ResolutionTaskGroup[] {
  const grouped = new Map<string, ResolutionTask[]>();
  for (const task of tasks) {
    if (!task.groupKey || task.groupingScope === "NONE") continue;
    const group = grouped.get(task.groupKey) ?? [];
    group.push(task);
    grouped.set(task.groupKey, group);
  }

  return Array.from(grouped.entries())
    .map(([groupKey, group]) => ({
      groupKey,
      semanticType: group[0]?.semanticType ?? null,
      question: group[0]?.question ?? null,
      applicationIds: uniqueStrings(group.map((task) => task.applicationId)),
      taskIds: group.map((task) => task.taskId),
      tasks: group,
    }))
    .sort((left, right) => left.groupKey.localeCompare(right.groupKey));
}
