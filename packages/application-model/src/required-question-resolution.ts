import type { Question, SemanticType } from "@munshi-apply/contracts";
import {
  createResolutionTask,
  resolutionPolicy,
  type ResolutionTask,
  type ResolutionTaskCategory,
} from "./resolution-task";

export const requiredQuestionResolutionStates = [
  "MISSING",
  "REVIEW",
  "READY",
] as const;
export type RequiredQuestionResolutionState =
  (typeof requiredQuestionResolutionStates)[number];

export type RequiredQuestionResolutionObservation = {
  question: Question;
  state: RequiredQuestionResolutionState;
};

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

function optionalString(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function timestamp(value: string, label: string): string {
  const normalized = requiredString(value, label);
  if (Number.isNaN(Date.parse(normalized))) {
    throw new Error(`${label} must be an ISO-compatible timestamp`);
  }
  return normalized;
}

function categoryFor(
  state: Exclude<RequiredQuestionResolutionState, "READY">,
  semanticType: SemanticType,
): ResolutionTaskCategory {
  if (semanticType === "UNKNOWN") return "AMBIGUOUS_QUESTION";
  return state === "MISSING" ? "MISSING_FACT" : "LOW_CONFIDENCE";
}

function reasonFor(
  state: Exclude<RequiredQuestionResolutionState, "READY">,
): string {
  return state === "MISSING"
    ? "Required application question does not yet have a candidate answer"
    : "Required application answer exists but has not been approved for AutoPilot";
}

export function requiredQuestionResolutionTaskId(
  applicationId: string,
  questionId: string,
): string {
  const application = requiredString(applicationId, "applicationId");
  const question = requiredString(questionId, "questionId");
  return `resolution-question-${stableHash(`${application}|${question}`)}`;
}

/**
 * Creates one durable task for the unresolved state of a required application
 * question. Session/checkpoint/page references are deliberately excluded from
 * task identity so the same owner work survives rescans and recovery.
 */
export function durableResolutionTaskFromRequiredQuestion(input: {
  applicationId: string;
  observation: RequiredQuestionResolutionObservation;
  sessionId?: string | null;
  checkpointId?: string | null;
  pageId?: string | null;
  createdAt: string;
}): ResolutionTask | null {
  if (input.observation.state === "READY") return null;
  const { question, state } = input.observation;
  return createResolutionTask({
    taskId: requiredQuestionResolutionTaskId(
      input.applicationId,
      question.questionId,
    ),
    applicationId: input.applicationId,
    sessionId: optionalString(input.sessionId),
    checkpointId: optionalString(input.checkpointId),
    pageId: optionalString(input.pageId),
    controlId: question.controlId,
    questionId: question.questionId,
    question: question.rawText,
    semanticType: question.semanticType,
    category: categoryFor(state, question.semanticType),
    reason: reasonFor(state),
    sourceRefs: [`question:${question.questionId}`],
    createdAt: input.createdAt,
  });
}

/**
 * Refreshes a nonterminal required-question task without changing its logical
 * question identity or losing resolver progress. A READY observation is
 * handled by the sync layer as an explicit supersession/expiration event.
 */
export function reconcileRequiredQuestionResolutionTask(
  existing: ResolutionTask,
  input: {
    observation: RequiredQuestionResolutionObservation;
    sessionId?: string | null;
    checkpointId?: string | null;
    pageId?: string | null;
    updatedAt: string;
  },
): ResolutionTask {
  if (["RESOLVED", "FAILED", "EXPIRED"].includes(existing.status)) {
    return existing;
  }
  if (input.observation.state === "READY") {
    throw new Error("READY required questions do not require task reconciliation");
  }
  const expectedTaskId = requiredQuestionResolutionTaskId(
    existing.applicationId,
    input.observation.question.questionId,
  );
  if (existing.taskId !== expectedTaskId) {
    throw new Error(
      "Existing Resolution Task does not match this required question",
    );
  }
  const updatedAt = timestamp(input.updatedAt, "updatedAt");
  if (Date.parse(updatedAt) < Date.parse(existing.updatedAt)) {
    throw new Error("Resolution task updates must be monotonic");
  }

  const category = categoryFor(
    input.observation.state,
    existing.semanticType ?? "UNKNOWN",
  );
  const policy = resolutionPolicy({
    category,
    semanticType: existing.semanticType,
  });

  return {
    ...existing,
    sessionId: optionalString(input.sessionId) ?? existing.sessionId,
    checkpointId: optionalString(input.checkpointId) ?? existing.checkpointId,
    pageId: optionalString(input.pageId) ?? existing.pageId,
    controlId:
      optionalString(input.observation.question.controlId) ?? existing.controlId,
    questionId: existing.questionId ?? input.observation.question.questionId,
    category,
    riskLevel: policy.riskLevel,
    autoResolvable: policy.allowAutomaticResolution,
    requiresUser:
      existing.status === "WAITING_FOR_USER" || policy.requiresUser,
    reason: reasonFor(input.observation.state),
    updatedAt,
  };
}
