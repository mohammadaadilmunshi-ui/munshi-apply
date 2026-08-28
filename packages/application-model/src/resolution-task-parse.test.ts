import { describe, expect, it } from "vitest";
import { parseResolutionTask, parseResolutionTasks } from "./resolution-task-parse";

const pendingTask = {
  schemaVersion: 1,
  taskId: "resolution-1",
  applicationId: "application-1",
  sessionId: "session-1",
  checkpointId: "checkpoint-1",
  pageId: "page-1",
  controlId: "control-1",
  questionId: "question-1",
  question: "Are you willing to relocate?",
  semanticType: "RELOCATION",
  category: "MISSING_FACT",
  status: "PENDING",
  riskLevel: "LOW",
  autoResolvable: true,
  requiresUser: false,
  groupingScope: "SEMANTIC",
  groupKey: "semantic:RELOCATION",
  sourceRefs: ["requirement-1"],
  evidenceRefs: [],
  attemptedResolvers: [],
  reason: "Relocation preference is not confirmed",
  resolution: null,
  createdAt: "2026-08-28T18:00:00.000Z",
  updatedAt: "2026-08-28T18:00:00.000Z",
};

describe("Resolution Task persistence parser", () => {
  it("accepts a canonical persisted task", () => {
    expect(parseResolutionTask(pendingTask)).toEqual(pendingTask);
    expect(parseResolutionTasks([pendingTask])).toEqual([pendingTask]);
  });

  it("rejects malformed grouping state", () => {
    expect(() =>
      parseResolutionTask({
        ...pendingTask,
        groupingScope: "NONE",
      }),
    ).toThrow("cannot have a groupKey");
  });

  it("rejects policy drift in persisted risk and automatic-resolution flags", () => {
    expect(() =>
      parseResolutionTask({ ...pendingTask, riskLevel: "HIGH" }),
    ).toThrow("riskLevel conflicts");
    expect(() =>
      parseResolutionTask({ ...pendingTask, autoResolvable: false }),
    ).toThrow("autoResolvable conflicts");
  });

  it("rejects high-risk AI resolver attempts", () => {
    expect(() =>
      parseResolutionTask({
        ...pendingTask,
        semanticType: "SPONSORSHIP_FUTURE",
        riskLevel: "HIGH",
        attemptedResolvers: ["GROUNDED_AI"],
      }),
    ).toThrow("not permitted");
  });

  it("accepts a checkpoint-preserving user resolution", () => {
    const resolved = parseResolutionTask({
      ...pendingTask,
      status: "RESOLVED",
      evidenceRefs: ["evidence-1"],
      attemptedResolvers: ["USER"],
      resolution: {
        value: "Yes",
        source: "USER",
        evidenceRefs: ["evidence-1"],
        approvedByUser: true,
        resolvedAt: "2026-08-28T18:02:00.000Z",
      },
      updatedAt: "2026-08-28T18:02:00.000Z",
    });

    expect(resolved.status).toBe("RESOLVED");
    expect(resolved.checkpointId).toBe("checkpoint-1");
    expect(resolved.resolution?.value).toBe("Yes");
  });

  it("requires user approval for legal and blocking resolutions", () => {
    expect(() =>
      parseResolutionTask({
        ...pendingTask,
        semanticType: "SPONSORSHIP_FUTURE",
        category: "LEGAL_CONFIRMATION",
        status: "RESOLVED",
        riskLevel: "HIGH",
        autoResolvable: false,
        groupingScope: "EXACT_QUESTION",
        groupKey: "question:will you require sponsorship",
        attemptedResolvers: ["MASTER_PROFILE"],
        resolution: {
          value: "No",
          source: "MASTER_PROFILE",
          evidenceRefs: [],
          approvedByUser: false,
          resolvedAt: "2026-08-28T18:02:00.000Z",
        },
        updatedAt: "2026-08-28T18:02:00.000Z",
      }),
    ).toThrow("requires explicit user approval");
  });

  it("rejects timezone-less persistence timestamps", () => {
    expect(() =>
      parseResolutionTask({
        ...pendingTask,
        updatedAt: "2026-08-28T18:02:00",
      }),
    ).toThrow("timezone-aware ISO timestamp");
  });
});
