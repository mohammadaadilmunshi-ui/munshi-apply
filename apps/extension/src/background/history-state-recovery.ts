import type { ApplicationPage } from "@munshi-apply/contracts";

export type HistoryStateRescanPlan = {
  clearWholeTab: boolean;
  frameIds: number[];
};

export type HistoryStateRecoveryDependencies = {
  getPages(tabId: number): Promise<ApplicationPage[]>;
  clearTab(tabId: number): Promise<void>;
  deleteFrame(tabId: number, frameId: number): Promise<void>;
  scanFrame(tabId: number, frameId: number): Promise<void>;
};

export function planHistoryStateRescan(
  changedFrameId: number,
  knownPages: readonly ApplicationPage[],
): HistoryStateRescanPlan {
  if (!Number.isSafeInteger(changedFrameId) || changedFrameId < 0) {
    return { clearWholeTab: false, frameIds: [] };
  }

  if (changedFrameId !== 0) {
    return { clearWholeTab: false, frameIds: [changedFrameId] };
  }

  const knownFrameIds = knownPages
    .map((page) => page.frameId)
    .filter((frameId) => Number.isSafeInteger(frameId) && frameId >= 0);
  return {
    clearWholeTab: true,
    frameIds: [...new Set([0, ...knownFrameIds])].sort(
      (left, right) => left - right,
    ),
  };
}

export async function recoverHistoryStateChange(
  tabId: number,
  changedFrameId: number,
  dependencies: HistoryStateRecoveryDependencies,
): Promise<void> {
  if (!Number.isSafeInteger(tabId) || tabId < 0) return;
  const knownPages = await dependencies.getPages(tabId);
  const plan = planHistoryStateRescan(changedFrameId, knownPages);
  if (plan.frameIds.length === 0) return;

  if (plan.clearWholeTab) {
    await dependencies.clearTab(tabId);
  } else {
    await dependencies.deleteFrame(tabId, changedFrameId);
  }

  for (const frameId of plan.frameIds) {
    try {
      await dependencies.scanFrame(tabId, frameId);
    } catch (error) {
      if (frameId === 0 || frameId === changedFrameId) throw error;
    }
  }
}
