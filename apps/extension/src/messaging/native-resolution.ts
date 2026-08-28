import {
  parseResolutionTask,
  parseResolutionTasks,
  resolutionTaskStatuses,
  type ResolutionTask,
  type ResolutionTaskStatus,
} from "@munshi-apply/application-model";
import { createNativeRequestBroker } from "./native-transport";

const nativeHostName = "systems.munshi.apply";
const statusSet = new Set<string>(resolutionTaskStatuses);
const nativeResolutionBroker = createNativeRequestBroker({
  connect: () => chrome.runtime.connectNative(nativeHostName),
  getLastErrorMessage: () => chrome.runtime.lastError?.message,
  idleDisconnectMilliseconds: 2_000,
});

export type NativeResolutionTaskSaveResult = {
  created: boolean;
  task: ResolutionTask;
};

export type NativeResolutionTaskListFilters = {
  applicationId?: string | null;
  status?: ResolutionTaskStatus | null;
  groupKey?: string | null;
  limit?: number;
};

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value.trim();
}

function parseSaveResult(value: unknown): NativeResolutionTaskSaveResult {
  const candidate = objectValue(value, "Native Resolution Task save response");
  if (typeof candidate.created !== "boolean") {
    throw new Error(
      "Native Resolution Task save response.created must be boolean",
    );
  }
  return {
    created: candidate.created,
    task: parseResolutionTask(candidate.task),
  };
}

export async function upsertNativeResolutionTask(
  task: ResolutionTask,
): Promise<NativeResolutionTaskSaveResult> {
  const canonical = parseResolutionTask(task);
  return parseSaveResult(
    await nativeResolutionBroker.request<unknown>({
      type: "UPSERT_RESOLUTION_TASK",
      payload: canonical,
    }),
  );
}

export async function getNativeResolutionTask(
  taskId: string,
): Promise<ResolutionTask | null> {
  const normalizedTaskId = requiredString(taskId, "Resolution taskId");
  const response = await nativeResolutionBroker.request<unknown>({
    type: "GET_RESOLUTION_TASK",
    payload: { taskId: normalizedTaskId },
  });
  return response === null ? null : parseResolutionTask(response);
}

export async function listNativeResolutionTasks(
  filters: NativeResolutionTaskListFilters = {},
): Promise<ResolutionTask[]> {
  const payload: Record<string, unknown> = {};
  if (filters.applicationId != null) {
    payload.applicationId = requiredString(
      filters.applicationId,
      "Resolution applicationId",
    );
  }
  if (filters.groupKey != null) {
    payload.groupKey = requiredString(filters.groupKey, "Resolution groupKey");
  }
  if (filters.status != null) {
    if (!statusSet.has(filters.status)) {
      throw new Error("Resolution status filter is invalid");
    }
    payload.status = filters.status;
  }
  if (filters.limit !== undefined) {
    if (
      !Number.isSafeInteger(filters.limit) ||
      filters.limit < 1 ||
      filters.limit > 500
    ) {
      throw new Error("Resolution Task list limit must be between 1 and 500");
    }
    payload.limit = filters.limit;
  }

  return parseResolutionTasks(
    await nativeResolutionBroker.request<unknown>({
      type: "LIST_RESOLUTION_TASKS",
      payload,
    }),
  );
}
