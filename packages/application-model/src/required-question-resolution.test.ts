import type { Question } from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import { recordResolutionAttempt } from "./resolution-task";
import {
  durableResolutionTaskFromRequiredQuestion,
  reconcileRequiredQuestionResolutionTask,
  requiredQuestionResolutionTaskId,
  type RequiredQuestionResolutionObservation,
} from "./required-question-resolution";

const question: Question = {
  questionId: "question-relocation",
  controlId: "control-relocation",
  rawText: "Are you willing to relocate?",
  semanticType: "RELOCATION",
  confidence: 0.99,
  sensitive: false,
  requiresReview: false,
};

function observation(
  state: RequiredQuestionResolutionObservation["state"],
): RequiredQuestionResolutionObservation {
  return { question, state };
}

describe("required question Resolution Task lifecycle", () => {
  it("keeps task identity stable across session and checkpoint changes", () => {
    const first = durableResolutionTaskFromRequiredQuestion({
      applicationId: "application-a",
      observation: observation("MISSING"),
      sessionId: "session-1",
      checkpointId: "checkpoint-1",
      pageId: "page-1",
      createdAt: "2026-08-28T19:10:00.000Z",
    });
    const second = durableResolutionTaskFromRequiredQuestion({
      applicationId: "application-a",
      observation: observation("MISSING"),
      sessionId: "session-2",
      checkpointId: "checkpoint-2",
      pageId: "page-2",
      createdAt: "2026-08-28T19:10:00.000Z",
    });

    expect(first?.taskId).toBe(second?.taskId);
    expect(first?.taskId).toBe(
      requiredQuestionResolutionTaskId(
        "application-a",
        "question-relocation",
      ),
    );
    expect(first).toMatchObject({
      category: "MISSING_FACT",
      questionId: "question-relocation",
      controlId: "control-relocation",
      sourceRefs: ["question:question-relocation"],
    });
  });

  it("reclassifies missing work to review without losing resolver progress", () => {
    const created = durableResolutionTaskFromRequiredQuestion({
      applicationId: "application-a",
      observation: observation("MISSING"),
      sessionId: "session-1",
      checkpointId: "checkpoint-1",
      pageId: "page-1",
      createdAt: "2026-08-28T19:10:00.000Z",
    });
    expect(created).not.toBeNull();
    const attempted = recordResolutionAttempt(
      created!,
      "MASTER_PROFILE",
      "2026-08-28T19:10:01.000Z",
    );

    const refreshed = reconcileRequiredQuestionResolutionTask(attempted, {
      observation: observation("REVIEW"),
      sessionId: "session-2",
      checkpointId: "checkpoint-2",
      pageId: "page-2",
      updatedAt: "2026-08-28T19:10:02.000Z",
    });

    expect(refreshed).toMatchObject({
      taskId: created!.taskId,
      category: "LOW_CONFIDENCE",
      status: "RESOLVING",
      sessionId: "session-2",
      checkpointId: "checkpoint-2",
      pageId: "page-2",
      attemptedResolvers: ["MASTER_PROFILE"],
    });
  });

  it("classifies unknown required questions as ambiguous rather than generic missing facts", () => {
    const task = durableResolutionTaskFromRequiredQuestion({
      applicationId: "application-a",
      observation: {
        question: {
          ...question,
          questionId: "question-unknown",
          controlId: "control-unknown",
          rawText: "Please provide the requested information",
          semanticType: "UNKNOWN",
          confidence: 0.2,
          requiresReview: true,
        },
        state: "MISSING",
      },
      createdAt: "2026-08-28T19:10:00.000Z",
    });

    expect(task).toMatchObject({
      category: "AMBIGUOUS_QUESTION",
      riskLevel: "MEDIUM",
    });
  });

  it("does not create a task for an approved READY required question", () => {
    expect(
      durableResolutionTaskFromRequiredQuestion({
        applicationId: "application-a",
        observation: observation("READY"),
        createdAt: "2026-08-28T19:10:00.000Z",
      }),
    ).toBeNull();
  });
});
