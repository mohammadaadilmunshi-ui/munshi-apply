import {
  groupResolutionTasks,
  type ResolutionRiskLevel,
  type ResolutionTask,
  type ResolutionTaskCategory,
  type ResolutionTaskStatus,
} from "@munshi-apply/application-model";

const openStatuses = new Set<ResolutionTaskStatus>([
  "PENDING",
  "RESOLVING",
  "WAITING_FOR_USER",
]);

export type ResolutionTaskQueueDisposition =
  | "OWNER_REQUIRED"
  | "GUARDED_RESOLUTION"
  | "REVIEW";

export type ResolutionTaskQueueRow = {
  taskId: string;
  title: string;
  reason: string;
  category: ResolutionTaskCategory;
  categoryLabel: string;
  status: ResolutionTaskStatus;
  statusLabel: string;
  riskLevel: ResolutionRiskLevel;
  disposition: ResolutionTaskQueueDisposition;
  dispositionLabel: string;
  reusableApplicationCount: number;
  semanticType: ResolutionTask["semanticType"];
  updatedAt: string;
};

export type ResolutionTaskQueueView = {
  rows: readonly ResolutionTaskQueueRow[];
  currentOpenCount: number;
  ownerRequiredCount: number;
  guardedResolutionCount: number;
  reusableGroupCount: number;
  otherApplicationOpenCount: number;
  totalOpenCount: number;
};

function words(value: string): string {
  const normalized = value.replaceAll("_", " ").toLocaleLowerCase("en-US");
  return normalized.charAt(0).toLocaleUpperCase("en-US") + normalized.slice(1);
}

function categoryLabel(category: ResolutionTaskCategory): string {
  switch (category) {
    case "MISSING_FACT":
      return "Missing fact";
    case "AMBIGUOUS_QUESTION":
      return "Ambiguous question";
    case "LOW_CONFIDENCE":
      return "Low confidence";
    case "AUTHENTICATION":
      return "Authentication";
    case "EMAIL_VERIFICATION":
      return "Email verification";
    case "INTERACTION_FAILURE":
      return "Interaction recovery";
    case "DOCUMENT_REQUIRED":
      return "Document required";
    case "LEGAL_CONFIRMATION":
      return "Legal confirmation";
    case "CAPTCHA":
      return "Human verification";
    case "EXTERNAL_ACTION":
      return "External action";
    case "TEMPORARY_FAILURE":
      return "Temporary failure";
    case "BLOCKING_CONFLICT":
      return "Eligibility conflict";
  }
}

function disposition(task: ResolutionTask): ResolutionTaskQueueDisposition {
  if (task.requiresUser || task.status === "WAITING_FOR_USER") {
    return "OWNER_REQUIRED";
  }
  if (task.autoResolvable) return "GUARDED_RESOLUTION";
  return "REVIEW";
}

function dispositionLabel(value: ResolutionTaskQueueDisposition): string {
  switch (value) {
    case "OWNER_REQUIRED":
      return "Owner action required";
    case "GUARDED_RESOLUTION":
      return "Eligible for guarded resolution";
    case "REVIEW":
      return "Review required";
  }
}

function priority(task: ResolutionTask): number {
  if (task.requiresUser || task.status === "WAITING_FOR_USER") return 0;
  if (task.riskLevel === "HIGH") return 1;
  if (!task.autoResolvable) return 2;
  if (task.riskLevel === "MEDIUM") return 3;
  return 4;
}

function title(task: ResolutionTask): string {
  if (task.question?.trim()) return task.question.trim();
  if (task.semanticType) return words(task.semanticType);
  return categoryLabel(task.category);
}

export function isOpenResolutionTask(task: ResolutionTask): boolean {
  return openStatuses.has(task.status);
}

export function buildResolutionTaskQueueView(
  tasks: readonly ResolutionTask[],
  currentApplicationId: string,
): ResolutionTaskQueueView {
  const applicationId = currentApplicationId.trim();
  const open = tasks.filter(isOpenResolutionTask);
  const current = open.filter((task) => task.applicationId === applicationId);
  const reusableApplicationCounts = new Map<string, number>();
  const reusableCurrentGroups = new Set<string>();

  for (const group of groupResolutionTasks(open)) {
    if (group.applicationIds.length < 2) continue;
    reusableApplicationCounts.set(group.groupKey, group.applicationIds.length);
    if (group.tasks.some((task) => task.applicationId === applicationId)) {
      reusableCurrentGroups.add(group.groupKey);
    }
  }

  const rows = current
    .slice()
    .sort(
      (left, right) =>
        priority(left) - priority(right) ||
        Date.parse(right.updatedAt) - Date.parse(left.updatedAt) ||
        left.taskId.localeCompare(right.taskId),
    )
    .map((task): ResolutionTaskQueueRow => {
      const nextDisposition = disposition(task);
      return {
        taskId: task.taskId,
        title: title(task),
        reason: task.reason,
        category: task.category,
        categoryLabel: categoryLabel(task.category),
        status: task.status,
        statusLabel: words(task.status),
        riskLevel: task.riskLevel,
        disposition: nextDisposition,
        dispositionLabel: dispositionLabel(nextDisposition),
        reusableApplicationCount: task.groupKey
          ? (reusableApplicationCounts.get(task.groupKey) ?? 1)
          : 1,
        semanticType: task.semanticType,
        updatedAt: task.updatedAt,
      };
    });

  return {
    rows,
    currentOpenCount: current.length,
    ownerRequiredCount: current.filter(
      (task) => disposition(task) === "OWNER_REQUIRED",
    ).length,
    guardedResolutionCount: current.filter(
      (task) => disposition(task) === "GUARDED_RESOLUTION",
    ).length,
    reusableGroupCount: reusableCurrentGroups.size,
    otherApplicationOpenCount: open.length - current.length,
    totalOpenCount: open.length,
  };
}
