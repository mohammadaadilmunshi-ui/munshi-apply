import {
  durableResolutionTaskFromPreflightFinding,
  preflightResolutionTaskId,
  reconcilePreflightResolutionTask,
  type AutoPilotSession,
  type EmployerPreflightFinding,
  type ResolutionTask,
} from "@munshi-apply/application-model";
import type { ApplicationPage, Question } from "@munshi-apply/contracts";
import {
  listNativeResolutionTasks,
  upsertNativeResolutionTask,
} from "../messaging/native-resolution";

export type PreflightResolutionSyncInput = {
  applicationId: string;
  page: ApplicationPage;
  findings: readonly EmployerPreflightFinding[];
  session: AutoPilotSession | null;
  observedAt: string;
};

function compact(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function normalize(value: string): string {
  return compact(value).normalize("NFKC").toLocaleLowerCase("en-US");
}

function questionForFinding(
  page: ApplicationPage,
  finding: EmployerPreflightFinding,
): Question | null {
  const requirement = finding.requirement;
  if (requirement.sourceKind !== "APPLICATION_QUESTION") return null;
  const normalizedSource = normalize(requirement.sourceText);
  return (
    page.questions.find(
      (question) =>
        normalize(question.rawText) === normalizedSource &&
        (requirement.semanticType === null ||
          question.semanticType === requirement.semanticType),
    ) ?? null
  );
}

function sessionForApplication(
  session: AutoPilotSession | null,
  applicationId: string,
): AutoPilotSession | null {
  return session?.applicationId === applicationId ? session : null;
}

function strictlyLaterTimestamp(candidate: string, previous: string): string {
  const candidateTime = Date.parse(candidate);
  const previousTime = Date.parse(previous);
  if (Number.isNaN(candidateTime) || Number.isNaN(previousTime)) {
    throw new Error("Resolution Task sync timestamps must be valid ISO timestamps");
  }
  return new Date(Math.max(candidateTime, previousTime + 1)).toISOString();
}

function materialFingerprint(task: ResolutionTask): string {
  return JSON.stringify({
    taskId: task.taskId,
    applicationId: task.applicationId,
    sessionId: task.sessionId,
    checkpointId: task.checkpointId,
    pageId: task.pageId,
    controlId: task.controlId,
    questionId: task.questionId,
    question: task.question,
    semanticType: task.semanticType,
    category: task.category,
    status: task.status,
    riskLevel: task.riskLevel,
    autoResolvable: task.autoResolvable,
    requiresUser: task.requiresUser,
    groupingScope: task.groupingScope,
    groupKey: task.groupKey,
    sourceRefs: task.sourceRefs,
    evidenceRefs: task.evidenceRefs,
    attemptedResolvers: task.attemptedResolvers,
    reason: task.reason,
    resolution: task.resolution,
    createdAt: task.createdAt,
  });
}

export function planPreflightResolutionTaskSync(
  input: PreflightResolutionSyncInput,
  existingTasks: readonly ResolutionTask[],
): ResolutionTask[] {
  const existingById = new Map(existingTasks.map((task) => [task.taskId, task]));
  const session = sessionForApplication(input.session, input.applicationId);
  const writes: ResolutionTask[] = [];

  for (const finding of input.findings) {
    if (finding.state === "READY") continue;
    const question = questionForFinding(input.page, finding);
    const taskId = preflightResolutionTaskId(
      input.applicationId,
      finding.requirement.requirementId,
    );
    const existing = existingById.get(taskId);

    if (!existing) {
      const created = durableResolutionTaskFromPreflightFinding({
        finding,
        applicationId: input.applicationId,
        sessionId: session?.sessionId ?? null,
        checkpointId: session?.lastCheckpointId ?? null,
        pageId: input.page.pageId,
        controlId: question?.controlId ?? null,
        questionId: question?.questionId ?? null,
        createdAt: input.observedAt,
      });
      if (created) writes.push(created);
      continue;
    }

    if (["RESOLVED", "FAILED", "EXPIRED"].includes(existing.status)) continue;
    const refreshed = reconcilePreflightResolutionTask(existing, {
      finding,
      sessionId: session?.sessionId ?? null,
      checkpointId: session?.lastCheckpointId ?? null,
      pageId: input.page.pageId,
      controlId: question?.controlId ?? null,
      questionId: question?.questionId ?? null,
      updatedAt: strictlyLaterTimestamp(input.observedAt, existing.updatedAt),
    });
    if (materialFingerprint(refreshed) !== materialFingerprint(existing)) {
      writes.push(refreshed);
    }
  }

  return writes;
}

export async function syncPreflightResolutionTasks(
  input: PreflightResolutionSyncInput,
): Promise<ResolutionTask[]> {
  const existing = await listNativeResolutionTasks({
    applicationId: input.applicationId,
    limit: 500,
  });
  const writes = planPreflightResolutionTaskSync(input, existing);
  for (const task of writes) {
    await upsertNativeResolutionTask(task);
  }
  return writes;
}
