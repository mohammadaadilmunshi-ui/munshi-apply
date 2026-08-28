import {
  createResolutionTask,
  waitForResolutionUser,
  type ResolutionTask,
} from "@munshi-apply/application-model";
import { describe, expect, it } from "vitest";
import {
  buildResolutionTaskQueueView,
  isOpenResolutionTask,
} from "./resolution-task-view";

function relocationTask(
  applicationId: string,
  createdAt: string,
): ResolutionTask {
  return createResolutionTask({
    applicationId,
    question: "Are you willing to relocate?",
    semanticType: "RELOCATION",
    category: "MISSING_FACT",
    reason: "Relocation preference is not confirmed",
    createdAt,
  });
}

function legalTask(applicationId: string, createdAt: string): ResolutionTask {
  return createResolutionTask({
    applicationId,
    question: "Will you require employment sponsorship in the future?",
    semanticType: "SPONSORSHIP_FUTURE",
    category: "LEGAL_CONFIRMATION",
    reason: "The sponsorship answer needs explicit owner confirmation",
    createdAt,
  });
}

describe("Resolution Task queue view", () => {
  it("keeps only active lifecycle states open", () => {
    const pending = relocationTask(
      "application-a",
      "2026-08-28T18:00:00.000Z",
    );
    expect(isOpenResolutionTask(pending)).toBe(true);
    expect(isOpenResolutionTask({ ...pending, status: "RESOLVED" })).toBe(
      false,
    );
    expect(isOpenResolutionTask({ ...pending, status: "FAILED" })).toBe(false);
    expect(isOpenResolutionTask({ ...pending, status: "EXPIRED" })).toBe(false);
  });

  it("prioritizes direct owner work ahead of lower-risk guarded candidates", () => {
    const guarded = relocationTask(
      "application-a",
      "2026-08-28T18:05:00.000Z",
    );
    const owner = legalTask(
      "application-a",
      "2026-08-28T18:00:00.000Z",
    );

    const view = buildResolutionTaskQueueView(
      [guarded, owner],
      "application-a",
    );

    expect(view.rows.map((row) => row.taskId)).toEqual([
      owner.taskId,
      guarded.taskId,
    ]);
    expect(view.rows[0]).toMatchObject({
      disposition: "OWNER_REQUIRED",
      riskLevel: "HIGH",
      categoryLabel: "Legal confirmation",
    });
    expect(view.rows[1]).toMatchObject({
      disposition: "GUARDED_RESOLUTION",
      riskLevel: "LOW",
    });
  });

  it("counts reusable semantic work across applications without merging tasks", () => {
    const current = relocationTask(
      "application-a",
      "2026-08-28T18:00:00.000Z",
    );
    const other = relocationTask(
      "application-b",
      "2026-08-28T18:01:00.000Z",
    );

    const view = buildResolutionTaskQueueView(
      [current, other],
      "application-a",
    );

    expect(view.currentOpenCount).toBe(1);
    expect(view.otherApplicationOpenCount).toBe(1);
    expect(view.totalOpenCount).toBe(2);
    expect(view.reusableGroupCount).toBe(1);
    expect(view.rows[0]?.reusableApplicationCount).toBe(2);
  });

  it("treats WAITING_FOR_USER as owner-required even for an otherwise auto-resolvable category", () => {
    const pending = relocationTask(
      "application-a",
      "2026-08-28T18:00:00.000Z",
    );
    const waiting = waitForResolutionUser(
      pending,
      "2026-08-28T18:01:00.000Z",
    );

    const view = buildResolutionTaskQueueView([waiting], "application-a");

    expect(view.ownerRequiredCount).toBe(1);
    expect(view.guardedResolutionCount).toBe(0);
    expect(view.rows[0]?.dispositionLabel).toBe("Owner action required");
  });

  it("does not surface terminal tasks from current or other applications", () => {
    const current = {
      ...relocationTask("application-a", "2026-08-28T18:00:00.000Z"),
      status: "EXPIRED" as const,
    };
    const other = {
      ...relocationTask("application-b", "2026-08-28T18:01:00.000Z"),
      status: "RESOLVED" as const,
    };

    expect(
      buildResolutionTaskQueueView([current, other], "application-a"),
    ).toMatchObject({
      rows: [],
      currentOpenCount: 0,
      otherApplicationOpenCount: 0,
      totalOpenCount: 0,
      reusableGroupCount: 0,
    });
  });
});
