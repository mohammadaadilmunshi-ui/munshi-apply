import type { ApplicationPage } from "@munshi-apply/contracts";

export type HistoryStateRescanPlan = {
  clearWholeTab: boolean;
  frameIds: number[];
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
    frameIds: [...new Set([0, ...knownFrameIds])].sort((left, right) => left - right),
  };
}
