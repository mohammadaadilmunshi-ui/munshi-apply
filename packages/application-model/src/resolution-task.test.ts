import { describe, expect, it } from "vitest";
import type { EmployerPreflightFinding } from "./employer-preflight";
import {
  createResolutionTask,
  groupResolutionTasks,
  recordResolutionAttempt,
  resolutionPolicy,
  resolutionTaskFromPreflightFinding,
  resolveResolutionTask,
  waitForResolutionUser,
} from "./resolution-task";

const now = "2026-08-28T16:00:00.000Z";

function relocationTask(applicationId: string, question: string) {
  return createResolutionTask({
    applicationId,
    sessionId: `session-${applicationId}`,
    checkpointId: `checkpoint-${applicationId}`,
    pageId: `page-${applicationId}`,
    questionId: `question-${applicationId}`,
    question,
    semanticType: "RELOCATION",
    category: "MISSING_FACT",
    reason: "Relocation preference is not confirmed",
    createdAt: now,
  });
}

describe("resolution task orchestration", () => {
  it("groups semantically equivalent reusable questions across applications", () => {
    const first = relocationTask(
      "application-a",
      "Are you willing to relocate?",
    );
    const second = relocationTask(
      "application-b",
      "Would you relocate for this position?",
    );

    expect(first.groupingScope).toBe("SEMANTIC");
    expect(first.groupKey).toBe("semantic:RELOCATION");
    expect(second.groupKey).toBe(first.groupKey);

    const groups = groupResolutionTasks([first, second]);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.applicationIds).toEqual([
      "application-a",
      "application-b",
    ]);
    expect(groups[0]?.tasks).toHaveLength(2);
  });

  it("keeps employer-specific narrative questions scoped to exact wording", () => {
    const first = createResolutionTask({
      applicationId: "application-a",
      question: "Why do you want to work for Alpha?",
      semanticType: "WHY_COMPANY",
      category: "LOW_CONFIDENCE",
      reason: "Narrative answer needs review",
      createdAt: now,
    });
    const second = createResolutionTask({
      applicationId: "application-b",
      question: "Why do you want to work for Beta?",
      semanticType: "WHY_COMPANY",
      category: "LOW_CONFIDENCE",
      reason: "Narrative answer needs review",
      createdAt: now,
    });

    expect(first.groupingScope).toBe("EXACT_QUESTION");
    expect(second.groupingScope).toBe("EXACT_QUESTION");
    expect(first.groupKey).not.toBe(second.groupKey);
  });

  it("never offers AI as a resolver for high-risk work authorization facts", () => {
    const policy = resolutionPolicy({
      category: "MISSING_FACT",
      semanticType: "WORK_AUTHORIZATION_CURRENT",
    });

    expect(policy.riskLevel).toBe("HIGH");
    expect(policy.resolverStages).toContain("MASTER_PROFILE");
    expect(policy.resolverStages).toContain("EVIDENCE_GRAPH");
    expect(policy.resolverStages).toContain("USER");
    expect(policy.resolverStages).not.toContain("GROUNDED_AI");
    expect(policy.resolverStages).not.toContain("DETERMINISTIC_DERIVATION");
  });

  it("requires direct user handling for CAPTCHA and does not deduplicate it", () => {
    const task = createResolutionTask({
      applicationId: "application-a",
      category: "CAPTCHA",
      reason: "Employer requires human verification",
      createdAt: now,
    });

    expect(task.riskLevel).toBe("HIGH");
    expect(task.requiresUser).toBe(true);
    expect(task.autoResolvable).toBe(false);
    expect(task.groupingScope).toBe("NONE");
    expect(task.groupKey).toBeNull();
    expect(resolutionPolicy(task).resolverStages).toEqual(["USER"]);
  });

  it("preserves the application checkpoint while an asynchronous user resolution completes", () => {
    const task = relocationTask(
      "application-a",
      "Are you willing to relocate?",
    );
    const attempted = recordResolutionAttempt(
      task,
      "MASTER_PROFILE",
      "2026-08-28T16:00:01.000Z",
    );
    const waiting = waitForResolutionUser(
      attempted,
      "2026-08-28T16:00:02.000Z",
    );
    const resolved = resolveResolutionTask(waiting, {
      value: "Yes",
      source: "USER",
      approvedByUser: true,
      evidenceRefs: ["evidence-relocation-preference"],
      resolvedAt: "2026-08-28T16:00:03.000Z",
    });

    expect(resolved.status).toBe("RESOLVED");
    expect(resolved.checkpointId).toBe("checkpoint-application-a");
    expect(resolved.sessionId).toBe("session-application-a");
    expect(resolved.resolution).toMatchObject({
      value: "Yes",
      source: "USER",
      approvedByUser: true,
    });
    expect(resolved.attemptedResolvers).toEqual(["MASTER_PROFILE", "USER"]);
  });

  it("converts unresolved preflight findings into checkpoint-aware tasks and ignores READY findings", () => {
    const finding: EmployerPreflightFinding = {
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

    const task = resolutionTaskFromPreflightFinding({
      finding,
      applicationId: "application-a",
      sessionId: "session-a",
      checkpointId: "checkpoint-a",
      pageId: "page-a",
      createdAt: now,
    });

    expect(task).toMatchObject({
      applicationId: "application-a",
      sessionId: "session-a",
      checkpointId: "checkpoint-a",
      semanticType: "SPONSORSHIP_FUTURE",
      category: "MISSING_FACT",
      riskLevel: "HIGH",
      sourceRefs: ["req-sponsorship"],
    });

    expect(
      resolutionTaskFromPreflightFinding({
        finding: { ...finding, state: "READY" },
        applicationId: "application-a",
        createdAt: now,
      }),
    ).toBeNull();
  });

  it("treats confirmed preflight conflicts as user-visible blockers rather than auto-fixable facts", () => {
    const finding: EmployerPreflightFinding = {
      requirement: {
        requirementId: "req-clearance",
        kind: "SECURITY_CLEARANCE",
        sourceKind: "JOB_CONTEXT",
        sourceText: "Active Secret clearance is required.",
        semanticType: "SECURITY_CLEARANCE",
        expectedValues: ["Secret"],
        numericValue: null,
        unit: null,
        confidence: 0.97,
        consequential: true,
        knockout: true,
      },
      state: "BLOCKED",
      candidateValue: "No clearance",
      reason: "Confirmed clearance conflicts with employer requirement",
    };

    const task = resolutionTaskFromPreflightFinding({
      finding,
      applicationId: "application-a",
      createdAt: now,
    });

    expect(task).toMatchObject({
      category: "BLOCKING_CONFLICT",
      riskLevel: "HIGH",
      autoResolvable: false,
      requiresUser: true,
      groupingScope: "NONE",
    });
    expect(resolutionPolicy(task!).resolverStages).not.toContain("GROUNDED_AI");
  });
});
