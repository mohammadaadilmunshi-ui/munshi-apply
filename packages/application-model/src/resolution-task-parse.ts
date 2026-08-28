import { semanticTypes, type SemanticType } from "@munshi-apply/contracts";
import {
  RESOLUTION_TASK_SCHEMA_VERSION,
  resolutionPolicy,
  resolutionRiskLevels,
  resolutionTaskCategories,
  resolutionTaskStatuses,
  resolverStages,
  type ResolutionGroupingScope,
  type ResolutionRiskLevel,
  type ResolutionTask,
  type ResolutionTaskCategory,
  type ResolutionTaskResolution,
  type ResolutionTaskStatus,
  type ResolverStage,
} from "./resolution-task";

const categorySet = new Set<string>(resolutionTaskCategories);
const statusSet = new Set<string>(resolutionTaskStatuses);
const riskSet = new Set<string>(resolutionRiskLevels);
const resolverSet = new Set<string>(resolverStages);
const semanticTypeSet = new Set<string>(semanticTypes);
const groupingScopes = new Set<string>(["NONE", "EXACT_QUESTION", "SEMANTIC"]);

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value.trim();
}

function nullableString(value: unknown, label: string): string | null {
  if (value === null) return null;
  return requiredString(value, label);
}

function timestamp(value: unknown, label: string): string {
  const result = requiredString(value, label);
  if (
    Number.isNaN(Date.parse(result)) ||
    !/(?:Z|[+-]\d{2}:\d{2})$/i.test(result)
  ) {
    throw new Error(`${label} must be a timezone-aware ISO timestamp`);
  }
  return result;
}

function uniqueStrings(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  const result = value.map((item) => requiredString(item, label));
  if (new Set(result).size !== result.length) {
    throw new Error(`${label} must not contain duplicates`);
  }
  return result;
}

function parseResolverStages(value: unknown): ResolverStage[] {
  const values = uniqueStrings(value, "attemptedResolvers");
  for (const item of values) {
    if (!resolverSet.has(item)) {
      throw new Error(`Resolution resolver stage ${item} is invalid`);
    }
  }
  return values as ResolverStage[];
}

function parseResolution(value: unknown): ResolutionTaskResolution {
  const candidate = objectValue(value, "Resolution task resolution");
  const source = requiredString(candidate.source, "Resolution source");
  if (!resolverSet.has(source)) {
    throw new Error("Resolution source is invalid");
  }
  if (typeof candidate.approvedByUser !== "boolean") {
    throw new Error("Resolution approvedByUser must be boolean");
  }
  if (!("value" in candidate)) {
    throw new Error("Resolution value is required");
  }
  return {
    value: candidate.value,
    source: source as ResolverStage,
    evidenceRefs: uniqueStrings(
      candidate.evidenceRefs,
      "Resolution evidenceRefs",
    ),
    approvedByUser: candidate.approvedByUser,
    resolvedAt: timestamp(candidate.resolvedAt, "Resolution resolvedAt"),
  };
}

export function parseResolutionTask(value: unknown): ResolutionTask {
  const candidate = objectValue(value, "Resolution task");
  if (candidate.schemaVersion !== RESOLUTION_TASK_SCHEMA_VERSION) {
    throw new Error("Unsupported Resolution Task schema version");
  }

  const category = requiredString(candidate.category, "Resolution category");
  if (!categorySet.has(category))
    throw new Error("Resolution category is invalid");
  const status = requiredString(candidate.status, "Resolution status");
  if (!statusSet.has(status)) throw new Error("Resolution status is invalid");
  const riskLevel = requiredString(candidate.riskLevel, "Resolution riskLevel");
  if (!riskSet.has(riskLevel))
    throw new Error("Resolution riskLevel is invalid");
  const groupingScope = requiredString(
    candidate.groupingScope,
    "Resolution groupingScope",
  );
  if (!groupingScopes.has(groupingScope)) {
    throw new Error("Resolution groupingScope is invalid");
  }
  if (typeof candidate.autoResolvable !== "boolean") {
    throw new Error("Resolution autoResolvable must be boolean");
  }
  if (typeof candidate.requiresUser !== "boolean") {
    throw new Error("Resolution requiresUser must be boolean");
  }

  const semanticTypeValue = candidate.semanticType;
  let semanticType: SemanticType | null = null;
  if (semanticTypeValue !== null) {
    const normalized = requiredString(
      semanticTypeValue,
      "Resolution semanticType",
    );
    if (!semanticTypeSet.has(normalized)) {
      throw new Error("Resolution semanticType is invalid");
    }
    semanticType = normalized as SemanticType;
  }

  const groupKey = nullableString(candidate.groupKey, "Resolution groupKey");
  if (groupingScope === "NONE" && groupKey !== null) {
    throw new Error("Ungrouped Resolution Tasks cannot have a groupKey");
  }
  if (groupingScope !== "NONE" && groupKey === null) {
    throw new Error("Grouped Resolution Tasks require a groupKey");
  }

  const createdAt = timestamp(candidate.createdAt, "Resolution createdAt");
  const updatedAt = timestamp(candidate.updatedAt, "Resolution updatedAt");
  if (Date.parse(updatedAt) < Date.parse(createdAt)) {
    throw new Error("Resolution updatedAt cannot precede createdAt");
  }

  const attemptedResolvers = parseResolverStages(candidate.attemptedResolvers);
  const resolution =
    candidate.resolution === null
      ? null
      : parseResolution(candidate.resolution);
  if (status === "RESOLVED" && resolution === null) {
    throw new Error("Resolved Resolution Tasks require resolution details");
  }
  if (status !== "RESOLVED" && resolution !== null) {
    throw new Error(
      "Non-resolved Resolution Tasks cannot contain resolution details",
    );
  }
  if (status === "WAITING_FOR_USER" && candidate.requiresUser !== true) {
    throw new Error(
      "Resolution Tasks waiting for the user must require the user",
    );
  }

  const typedCategory = category as ResolutionTaskCategory;
  const policy = resolutionPolicy({ category: typedCategory, semanticType });
  if (riskLevel !== policy.riskLevel) {
    throw new Error("Resolution riskLevel conflicts with canonical policy");
  }
  if (candidate.autoResolvable !== policy.allowAutomaticResolution) {
    throw new Error(
      "Resolution autoResolvable conflicts with canonical policy",
    );
  }
  for (const stage of attemptedResolvers) {
    if (!policy.resolverStages.includes(stage)) {
      throw new Error(
        `Resolver stage ${stage} is not permitted for ${typedCategory}`,
      );
    }
  }
  if (resolution && !policy.resolverStages.includes(resolution.source)) {
    throw new Error(
      `Resolution source ${resolution.source} is not permitted for ${typedCategory}`,
    );
  }
  if (
    !policy.allowAutomaticResolution &&
    resolution &&
    resolution.source !== "USER" &&
    !resolution.approvedByUser
  ) {
    throw new Error(
      `${typedCategory} resolution requires explicit user approval`,
    );
  }

  return {
    schemaVersion: RESOLUTION_TASK_SCHEMA_VERSION,
    taskId: requiredString(candidate.taskId, "Resolution taskId"),
    applicationId: requiredString(
      candidate.applicationId,
      "Resolution applicationId",
    ),
    sessionId: nullableString(candidate.sessionId, "Resolution sessionId"),
    checkpointId: nullableString(
      candidate.checkpointId,
      "Resolution checkpointId",
    ),
    pageId: nullableString(candidate.pageId, "Resolution pageId"),
    controlId: nullableString(candidate.controlId, "Resolution controlId"),
    questionId: nullableString(candidate.questionId, "Resolution questionId"),
    question: nullableString(candidate.question, "Resolution question"),
    semanticType,
    category: typedCategory,
    status: status as ResolutionTaskStatus,
    riskLevel: riskLevel as ResolutionRiskLevel,
    autoResolvable: candidate.autoResolvable,
    requiresUser: candidate.requiresUser,
    groupingScope: groupingScope as ResolutionGroupingScope,
    groupKey,
    sourceRefs: uniqueStrings(candidate.sourceRefs, "Resolution sourceRefs"),
    evidenceRefs: uniqueStrings(
      candidate.evidenceRefs,
      "Resolution evidenceRefs",
    ),
    attemptedResolvers,
    reason: requiredString(candidate.reason, "Resolution reason"),
    resolution,
    createdAt,
    updatedAt,
  };
}

export function parseResolutionTasks(value: unknown): ResolutionTask[] {
  if (!Array.isArray(value))
    throw new Error("Resolution Task list must be an array");
  return value.map(parseResolutionTask);
}
