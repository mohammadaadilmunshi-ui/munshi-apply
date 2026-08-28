import type { ResolutionTask } from "@munshi-apply/application-model";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const timestamp = "2026-08-28T18:00:00.000Z";

function task(overrides: Partial<ResolutionTask> = {}): ResolutionTask {
  return {
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
    createdAt: timestamp,
    updatedAt: timestamp,
    ...overrides,
  };
}

function installNativePort(responses: unknown[]) {
  const messageListeners: Array<(value: unknown) => void> = [];
  const disconnectListeners: Array<() => void> = [];
  const postMessage = vi.fn(() => {
    const response = responses.shift();
    queueMicrotask(() => {
      for (const listener of messageListeners) listener(response);
    });
  });
  const port = {
    postMessage,
    disconnect: vi.fn(() => {
      for (const listener of disconnectListeners) listener();
    }),
    onMessage: {
      addListener: (listener: (value: unknown) => void) =>
        messageListeners.push(listener),
    },
    onDisconnect: {
      addListener: (listener: () => void) => disconnectListeners.push(listener),
    },
  };
  const connectNative = vi.fn(() => port);
  vi.stubGlobal("chrome", {
    runtime: { connectNative, lastError: undefined },
  });
  return { connectNative, postMessage };
}

async function nativeResolutionModule() {
  return import("./native-resolution");
}

describe("native Resolution Task client", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("validates and upserts a canonical task", async () => {
    const pending = task();
    const native = installNativePort([
      { ok: true, data: { created: true, task: pending } },
    ]);
    const { upsertNativeResolutionTask } = await nativeResolutionModule();

    await expect(upsertNativeResolutionTask(pending)).resolves.toEqual({
      created: true,
      task: pending,
    });
    expect(native.connectNative).toHaveBeenCalledWith("systems.munshi.apply");
    expect(native.postMessage).toHaveBeenCalledWith({
      type: "UPSERT_RESOLUTION_TASK",
      payload: pending,
    });
  });

  it("loads one task and validates the native payload", async () => {
    const pending = task();
    const native = installNativePort([{ ok: true, data: pending }]);
    const { getNativeResolutionTask } = await nativeResolutionModule();

    await expect(getNativeResolutionTask(" resolution-1 ")).resolves.toEqual(
      pending,
    );
    expect(native.postMessage).toHaveBeenCalledWith({
      type: "GET_RESOLUTION_TASK",
      payload: { taskId: "resolution-1" },
    });
  });

  it("lists tasks with bounded canonical filters", async () => {
    const pending = task();
    const native = installNativePort([{ ok: true, data: [pending] }]);
    const { listNativeResolutionTasks } = await nativeResolutionModule();

    await expect(
      listNativeResolutionTasks({
        applicationId: " application-1 ",
        status: "PENDING",
        groupKey: " semantic:RELOCATION ",
        limit: 25,
      }),
    ).resolves.toEqual([pending]);
    expect(native.postMessage).toHaveBeenCalledWith({
      type: "LIST_RESOLUTION_TASKS",
      payload: {
        applicationId: "application-1",
        status: "PENDING",
        groupKey: "semantic:RELOCATION",
        limit: 25,
      },
    });
  });

  it("rejects malformed native tasks instead of trusting them", async () => {
    installNativePort([{ ok: true, data: { ...task(), riskLevel: "HIGH" } }]);
    const { getNativeResolutionTask } = await nativeResolutionModule();

    await expect(getNativeResolutionTask("resolution-1")).rejects.toThrow(
      "riskLevel conflicts",
    );
  });

  it("rejects invalid list limits before opening the native companion", async () => {
    const native = installNativePort([]);
    const { listNativeResolutionTasks } = await nativeResolutionModule();

    await expect(listNativeResolutionTasks({ limit: 0 })).rejects.toThrow(
      "between 1 and 500",
    );
    expect(native.connectNative).not.toHaveBeenCalled();
  });
});
