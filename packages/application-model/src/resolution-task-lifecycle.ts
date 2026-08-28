import type { EmployerPreflightFinding } from "./employer-preflight";
import {
  resolutionTaskFromPreflightFinding,
  type ResolutionTask,
} from "./resolution-task";

function stableHash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function requiredString(value: string, label: string): string {
  const normalized = value.trim();
  if (!normalized) throw new Error(`${label} must be a non-empty string`);
  return normalized;
}

function timestamp(value: string, label: string): string {
  const normalized = requiredString(value, label);
  if (Number.isNaN(Date.parse(normalized))) {
    throw new Error(`${label} must be an ISO-compatible timestamp`);
  }
  return normalized;
}

function normalizedOptional(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

export function preflightResolutionTaskId(
  applicationId: string,
  requirementId: string,
): string {
  const application = requiredString(applicationId, "applicationId");
  const requirement = requiredString(requirementId, "requirementId");
  return `resolution-preflight-${stableHash(`${application}|${requirement}`)}`;
}

/**
 * Creates the durable task identity for one employer requirement. Unlike the
 * generic task factory, page/session/checkpoint identifiers are deliberately
 * excluded from this id so the same unresolved requirement can survive SPA
 * rerenders, new checkpoints, and AutoPilot recovery without duplicating work.
 */
export function durableResolutionTaskFromPreflightFinding(input: {
  finding: EmployerPreflightFinding;
  applicationId: string;
  sessionId?: string | null;
  checkpointId?: string | null;
  pageId?: string | null;
  controlId?: string | null;
  questionId?: string | null;
  createdAt: string;
}): ResolutionTask | null {
  const task = resolutionTaskFromPreflightFinding({
    finding: input.finding,
    applicationId: input.applicationId,
    sessionId: input.sessionId,
    checkpointId: input.checkpointId,
    pageId: input.pageId,
    createdAt: input.createdAt,
  });
  if (!task) return null;
  return {
    ...task,
    taskId: preflightResolutionTaskId(
      input.applicationId,
      input.finding.requirement.requirementId,
    ),
    controlId: normalizedOptional(input.controlId),
    questionId: normalizedOptional(input.questionId),
  };
}

/**
 * Re-evaluates an existing nonterminal preflight task against the latest page
 * while preserving resolver progress. Execution references are refreshable;
 * application/requirement identity and creation time are not.
 */
export function reconcilePreflightResolutionTask(
  existing: ResolutionTask,
  input: {
    finding: EmployerPreflightFinding;
    sessionId?: string | null;
    checkpointId?: string | null;
    pageId?: string | null;
    controlId?: string | null;
    questionId?: string | null;
    updatedAt: string;
  },
): ResolutionTask {
  if (["RESOLVED", "FAILED", "EXPIRED"].includes(existing.status)) {
    return existing;
  }
  const expectedTaskId = preflightResolutionTaskId(
    existing.applicationId,
    input.finding.requirement.requirementId,
  );
  if (existing.taskId !== expectedTaskId) {
    throw new Error("Existing Resolution Task does not match this employer requirement");
  }

  const refreshed = durableResolutionTaskFromPreflightFinding({
    finding: input.finding,
    applicationId: existing.applicationId,
    sessionId: normalizedOptional(input.sessionId) ?? existing.sessionId,
    checkpointId: normalizedOptional(input.checkpointId) ?? existing.checkpointId,
    pageId: normalizedOptional(input.pageId) ?? existing.pageId,
    controlId: normalizedOptional(input.controlId) ?? existing.controlId,
    questionId: normalizedOptional(input.questionId) ?? existing.questionId,
    createdAt: existing.createdAt,
  });
  if (!refreshed) {
    throw new Error("READY employer findings do not require task reconciliation");
  }

  const updatedAt = timestamp(input.updatedAt, "updatedAt");
  if (Date.parse(updatedAt) < Date.parse(existing.updatedAt)) {
    throw new Error("Resolution task updates must be monotonic");
  }

  return {
    ...refreshed,
    status: existing.status,
    requiresUser:
      existing.status === "WAITING_FOR_USER" || refreshed.requiresUser,
    evidenceRefs: existing.evidenceRefs,
    attemptedResolvers: existing.attemptedResolvers,
    resolution: existing.resolution,
    updatedAt,
  };
}
