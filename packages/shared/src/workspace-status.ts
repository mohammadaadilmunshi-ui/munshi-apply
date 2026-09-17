export type WorkspaceCountMetric =
  | { state: "loading" }
  | { state: "ready"; value: number }
  | { state: "error"; message: string };

export type WorkspaceSyncState =
  | { state: "idle" }
  | { state: "saving" }
  | { state: "synced"; acknowledgedAt: string }
  | { state: "retrying" }
  | { state: "error"; message: string };

export type WorkspaceAuthoritySnapshot = {
  activeDeviceCount: number;
  confirmedFactCount: number;
  encryptedResumeCount: number;
  answersToReviewCount: number;
  syncEventCount: number;
  historicalConflictCount: number;
  unresolvedConflictCount: number;
};

export type WorkspaceOverviewStatus = {
  activeDevices: WorkspaceCountMetric;
  confirmedFacts: WorkspaceCountMetric;
  encryptedResumes: WorkspaceCountMetric;
  answersToReview: WorkspaceCountMetric;
  syncEvents: WorkspaceCountMetric;
  historicalConflicts: WorkspaceCountMetric;
  unresolvedConflicts: WorkspaceCountMetric;
};

export type ConflictPresentation = {
  primaryLabel: string;
  primaryValue: string;
  secondaryText: string | null;
  requiresAttention: boolean;
};

export type ManualSyncPresentation = {
  visible: boolean;
  label: "Sync now" | "Retry sync";
  disabled: boolean;
};

function assertCount(value: number, name: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${name} must be a non-negative safe integer`);
  }
  return value;
}

function ready(value: number, name: string): WorkspaceCountMetric {
  return { state: "ready", value: assertCount(value, name) };
}

export function workspaceOverviewFromAuthority(
  snapshot: WorkspaceAuthoritySnapshot,
): WorkspaceOverviewStatus {
  return {
    activeDevices: ready(snapshot.activeDeviceCount, "activeDeviceCount"),
    confirmedFacts: ready(snapshot.confirmedFactCount, "confirmedFactCount"),
    encryptedResumes: ready(
      snapshot.encryptedResumeCount,
      "encryptedResumeCount",
    ),
    answersToReview: ready(
      snapshot.answersToReviewCount,
      "answersToReviewCount",
    ),
    syncEvents: ready(snapshot.syncEventCount, "syncEventCount"),
    historicalConflicts: ready(
      snapshot.historicalConflictCount,
      "historicalConflictCount",
    ),
    unresolvedConflicts: ready(
      snapshot.unresolvedConflictCount,
      "unresolvedConflictCount",
    ),
  };
}

export function loadingWorkspaceOverview(): WorkspaceOverviewStatus {
  const loading: WorkspaceCountMetric = { state: "loading" };
  return {
    activeDevices: loading,
    confirmedFacts: loading,
    encryptedResumes: loading,
    answersToReview: loading,
    syncEvents: loading,
    historicalConflicts: loading,
    unresolvedConflicts: loading,
  };
}

export function renderWorkspaceCount(metric: WorkspaceCountMetric): string {
  switch (metric.state) {
    case "loading":
      return "Loading…";
    case "ready":
      return String(metric.value);
    case "error":
      return "Unable to load";
  }
}

export function conflictPresentation(
  historical: WorkspaceCountMetric,
  unresolved: WorkspaceCountMetric,
): ConflictPresentation {
  if (unresolved.state !== "ready") {
    return {
      primaryLabel: "Unresolved conflicts",
      primaryValue: renderWorkspaceCount(unresolved),
      secondaryText:
        historical.state === "ready"
          ? `${historical.value} historical conflict event${historical.value === 1 ? "" : "s"}`
          : null,
      requiresAttention: false,
    };
  }

  const secondaryText =
    historical.state === "ready"
      ? `${historical.value} historical conflict event${historical.value === 1 ? "" : "s"}`
      : null;

  return {
    primaryLabel: "Unresolved conflicts",
    primaryValue: String(unresolved.value),
    secondaryText,
    requiresAttention: unresolved.value > 0,
  };
}

export function manualSyncPresentation(
  sync: WorkspaceSyncState,
): ManualSyncPresentation {
  switch (sync.state) {
    case "error":
      return { visible: true, label: "Retry sync", disabled: false };
    case "retrying":
      return { visible: true, label: "Retry sync", disabled: true };
    case "idle":
      return { visible: true, label: "Sync now", disabled: false };
    case "saving":
    case "synced":
      return { visible: false, label: "Sync now", disabled: true };
  }
}
