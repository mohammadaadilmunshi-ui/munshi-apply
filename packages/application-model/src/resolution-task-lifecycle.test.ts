import { describe, expect, it } from "vitest";
import type { EmployerPreflightFinding } from "./employer-preflight";
import {
  durableResolutionTaskFromPreflightFinding,
  preflightResolutionTaskId,
  reconcilePreflightResolutionTask,
} from "./resolution-task-lifecycle";
import { waitForResolutionUser } from "./resolution-task";

const unresolved: EmployerPreflightFinding = {
  requirement: {
    requirementId: "req-sponsorship",
    kind: "SPONSORSHIP",
    sourceKind: "APPLICATION_QUESTION",
    sourceText: "Will you require employment sponsorship in the future?",
    semanticType: "SPONSORSHIP_FUTURE",
    expectedValues: ["No"],
    numericValue: null,
    unit: null,
    confidence: 0.99,
    consequential: true,
    knockout: true,
  },
  state: "UNRESOLVED",
  candidateValue: null,
  reason: "A confirmed candidate answer is required",
};

describe("Resolution Task durable lifecycle", () => {
  it("keeps one stable task id across page, session, and checkpoint changes", () => {
    const first = durableResolutionTaskFromPreflightFinding({
      finding: unresolved,
      applicationId: "application-a",
      sessionId: "session-a",
      checkpointId: "checkpoint-a",
      pageId: "page-a",
      controlId: "control-a",
      questionId: "question-a",
      createdAt: "2026-08-28T18:30:00.000Z",
    });
    const second = durableResolutionTaskFromPreflightFinding({
      finding: unresolved,
      applicationId: "application-a",
      sessionId: "session-b",
      checkpointId: "checkpoint-b",
      pageId: "page-b",
      controlId: "control-b",
      questionId: "question-b",
      createdAt: "2026-08-28T18:31:00.000Z",
    });

    expect(first?.taskId).toBe(second?.taskId);
    expect(first?.taskId).toBe(
      preflightResolutionTaskId("application-a", "req-sponsorship"),
    );
  });

  it("refreshes resume context without losing resolver progress", () => {
    const initial = durableResolutionTaskFromPreflightFinding({
      finding: unresolved,
      applicationId: "application-a",
      sessionId: "session-a",
      checkpointId: "checkpoint-a",
      pageId: "page-a",
      createdAt: "2026-08-28T18:30:00.000Z",
    })!;
    const waiting = waitForResolutionUser(initial, "2026-08-28T18:30:30.000Z");
    const refreshed = reconcilePreflightResolutionTask(waiting, {
      finding: unresolved,
      sessionId: "session-b",
      checkpointId: "checkpoint-b",
      pageId: "page-b",
      controlId: "control-b",
      questionId: "question-b",
      updatedAt: "2026-08-28T18:31:00.000Z",
    });

    expect(refreshed).toMatchObject({
      taskId: initial.taskId,
      status: "WAITING_FOR_USER",
      requiresUser: true,
      sessionId: "session-b",
      checkpointId: "checkpoint-b",
      pageId: "page-b",
      controlId: "control-b",
      questionId: "question-b",
    });
  });

  it("allows the same requirement to become a stricter legal confirmation", () => {
    const initial = durableResolutionTaskFromPreflightFinding({
      finding: unresolved,
      applicationId: "application-a",
      createdAt: "2026-08-28T18:30:00.000Z",
    })!;
    const reviewFinding: EmployerPreflightFinding = {
      ...unresolved,
      state: "REVIEW",
      candidateValue: "No",
      reason: "The answer needs explicit owner confirmation",
    };
    const refreshed = reconcilePreflightResolutionTask(initial, {
      finding: reviewFinding,
      updatedAt: "2026-08-28T18:31:00.000Z",
    });

    expect(refreshed.taskId).toBe(initial.taskId);
    expect(refreshed.category).toBe("LEGAL_CONFIRMATION");
    expect(refreshed.riskLevel).toBe("HIGH");
    expect(refreshed.autoResolvable).toBe(false);
    expect(refreshed.requiresUser).toBe(true);
  });

  it("does not mutate terminal tasks during later page observations", () => {
    const initial = durableResolutionTaskFromPreflightFinding({
      finding: unresolved,
      applicationId: "application-a",
      createdAt: "2026-08-28T18:30:00.000Z",
    })!;
    const terminal = {
      ...initial,
      status: "FAILED" as const,
      updatedAt: "2026-08-28T18:31:00.000Z",
    };

    expect(
      reconcilePreflightResolutionTask(terminal, {
        finding: unresolved,
        pageId: "new-page",
        updatedAt: "2026-08-28T18:32:00.000Z",
      }),
    ).toBe(terminal);
  });

  it("rejects attempts to reconcile a different employer requirement", () => {
    const initial = durableResolutionTaskFromPreflightFinding({
      finding: unresolved,
      applicationId: "application-a",
      createdAt: "2026-08-28T18:30:00.000Z",
    })!;
    const other: EmployerPreflightFinding = {
      ...unresolved,
      requirement: {
        ...unresolved.requirement,
        requirementId: "req-other",
      },
    };

    expect(() =>
      reconcilePreflightResolutionTask(initial, {
        finding: other,
        updatedAt: "2026-08-28T18:31:00.000Z",
      }),
    ).toThrow("does not match this employer requirement");
  });
});
