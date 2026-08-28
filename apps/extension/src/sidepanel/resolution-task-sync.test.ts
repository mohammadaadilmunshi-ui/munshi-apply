import type {
  AutoPilotSession,
  EmployerPreflightFinding,
  ResolutionTask,
} from "@munshi-apply/application-model";
import type { ApplicationPage } from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import { planPreflightResolutionTaskSync } from "./resolution-task-sync";

const observedAt = "2026-08-28T18:40:00.000Z";

function page(): ApplicationPage {
  return {
    pageId: "page-1",
    tabId: 1,
    frameId: 0,
    documentId: "document-1",
    url: "https://example.com/apply",
    title: "Apply",
    observedAt,
    controls: [],
    questions: [
      {
        questionId: "question-sponsorship",
        controlId: "control-sponsorship",
        rawText: "Will you require employment sponsorship in the future?",
        semanticType: "SPONSORSHIP_FUTURE",
        confidence: 0.99,
        sensitive: true,
        requiresReview: true,
      },
    ],
    applicationState: "QUESTIONS",
    pageFingerprint: "fingerprint-1",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
  };
}

function finding(
  state: EmployerPreflightFinding["state"] = "UNRESOLVED",
): EmployerPreflightFinding {
  return {
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
    state,
    candidateValue: state === "UNRESOLVED" ? null : "No",
    reason:
      state === "REVIEW"
        ? "The answer needs explicit owner confirmation"
        : "A confirmed candidate answer is required",
  };
}

function session(overrides: Partial<AutoPilotSession> = {}): AutoPilotSession {
  return {
    schemaVersion: 1,
    sessionId: "session-1",
    applicationId: "application-1",
    applicationIdentity: "identity-1",
    status: "PAUSED_REVIEW",
    lastCheckpointSequence: 1,
    lastCheckpointId: "checkpoint-1",
    completedControlIds: [],
    pendingControlIds: ["control-sponsorship"],
    selectedResumeId: null,
    selectedResumeSha256: null,
    lastApplicationState: "QUESTIONS",
    lastPageId: "page-1",
    lastPageFingerprint: "fingerprint-1",
    securityCheckpoint: null,
    pauseReason: "Review required",
    updatedAt: observedAt,
    ...overrides,
  };
}

function firstWrite(
  findings: readonly EmployerPreflightFinding[] = [finding()],
  activeSession: AutoPilotSession | null = session(),
): ResolutionTask {
  const writes = planPreflightResolutionTaskSync(
    {
      applicationId: "application-1",
      page: page(),
      findings,
      session: activeSession,
      observedAt,
    },
    [],
  );
  expect(writes).toHaveLength(1);
  return writes[0]!;
}

describe("preflight Resolution Task sync planner", () => {
  it("creates one field-bound task for an actionable application question", () => {
    expect(firstWrite()).toMatchObject({
      applicationId: "application-1",
      sessionId: "session-1",
      checkpointId: "checkpoint-1",
      pageId: "page-1",
      controlId: "control-sponsorship",
      questionId: "question-sponsorship",
      category: "MISSING_FACT",
      semanticType: "SPONSORSHIP_FUTURE",
    });
  });

  it("produces zero writes for an unchanged status poll", () => {
    const existing = firstWrite();
    const writes = planPreflightResolutionTaskSync(
      {
        applicationId: "application-1",
        page: page(),
        findings: [finding()],
        session: session(),
        observedAt: "2026-08-28T18:40:01.000Z",
      },
      [existing],
    );

    expect(writes).toEqual([]);
  });

  it("refreshes only when the checkpoint or page context materially changes", () => {
    const existing = firstWrite();
    const nextPage = {
      ...page(),
      pageId: "page-2",
      observedAt: "2026-08-28T18:41:00.000Z",
    };
    const writes = planPreflightResolutionTaskSync(
      {
        applicationId: "application-1",
        page: nextPage,
        findings: [finding()],
        session: session({
          sessionId: "session-2",
          lastCheckpointId: "checkpoint-2",
        }),
        observedAt: nextPage.observedAt,
      },
      [existing],
    );

    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({
      taskId: existing.taskId,
      sessionId: "session-2",
      checkpointId: "checkpoint-2",
      pageId: "page-2",
    });
  });

  it("tightens the same logical requirement into legal confirmation", () => {
    const existing = firstWrite();
    const writes = planPreflightResolutionTaskSync(
      {
        applicationId: "application-1",
        page: page(),
        findings: [finding("REVIEW")],
        session: session(),
        observedAt: "2026-08-28T18:41:00.000Z",
      },
      [existing],
    );

    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({
      taskId: existing.taskId,
      category: "LEGAL_CONFIRMATION",
      riskLevel: "HIGH",
      autoResolvable: false,
      requiresUser: true,
    });
  });

  it("does not recreate or mutate terminal tasks", () => {
    const existing = {
      ...firstWrite(),
      status: "FAILED" as const,
      updatedAt: "2026-08-28T18:41:00.000Z",
    };
    const writes = planPreflightResolutionTaskSync(
      {
        applicationId: "application-1",
        page: { ...page(), pageId: "page-new" },
        findings: [finding()],
        session: session({ lastCheckpointId: "checkpoint-new" }),
        observedAt: "2026-08-28T18:42:00.000Z",
      },
      [existing],
    );

    expect(writes).toEqual([]);
  });

  it("ignores READY findings", () => {
    expect(
      planPreflightResolutionTaskSync(
        {
          applicationId: "application-1",
          page: page(),
          findings: [finding("READY")],
          session: session(),
          observedAt,
        },
        [],
      ),
    ).toEqual([]);
  });

  it("does not bind a session belonging to another application", () => {
    expect(
      firstWrite(
        [finding()],
        session({ applicationId: "different-application" }),
      ),
    ).toMatchObject({
      sessionId: null,
      checkpointId: null,
    });
  });

  it("keeps job-context findings free of synthetic field bindings", () => {
    const contextFinding: EmployerPreflightFinding = {
      ...finding(),
      requirement: {
        ...finding().requirement,
        requirementId: "req-context",
        sourceKind: "JOB_CONTEXT",
        sourceText: "This employer does not provide visa sponsorship.",
      },
    };
    const task = firstWrite([contextFinding], null);

    expect(task.controlId).toBeNull();
    expect(task.questionId).toBeNull();
  });
});
