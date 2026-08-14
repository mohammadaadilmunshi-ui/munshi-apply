import {
  applicationStates,
  securityCheckpointKinds,
  type ApplicationState,
  type SecurityCheckpointKind,
} from "@munshi-apply/contracts";
import {
  canResumeFromCheckpoint,
  createAutoPilotCheckpoint,
  parseAutoPilotCheckpoint,
  verifyNavigationAction,
  type AutoPilotCheckpoint,
  type AutoPilotObservation,
} from "./autopilot";

export const AUTO_PILOT_SESSION_SCHEMA_VERSION = 1 as const;

export const autoPilotSessionStatuses = [
  "IDLE",
  "RUNNING",
  "WAITING_RESCAN",
  "WAITING_NAVIGATION",
  "PAUSED_REVIEW",
  "PAUSED_SECURITY",
  "PAUSED_FINAL",
  "PAUSED_ERROR",
  "STOPPED",
] as const;
export type AutoPilotSessionStatus = (typeof autoPilotSessionStatuses)[number];

export type AutoPilotSession = {
  schemaVersion: typeof AUTO_PILOT_SESSION_SCHEMA_VERSION;
  sessionId: string;
  applicationId: string;
  applicationIdentity: string;
  status: AutoPilotSessionStatus;
  lastCheckpointSequence: number;
  lastCheckpointId: string | null;
  completedControlIds: readonly string[];
  pendingControlIds: readonly string[];
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
  lastApplicationState: ApplicationState | null;
  lastPageId: string | null;
  lastPageFingerprint: string | null;
  securityCheckpoint: SecurityCheckpointKind | null;
  pauseReason: string | null;
  updatedAt: string;
};

export type AutoPilotSessionAction =
  | { type: "START"; observation: AutoPilotObservation; at: string }
  | {
      type: "FILL_VERIFIED";
      controlId: string;
      pendingControlIds: readonly string[];
      at: string;
    }
  | {
      type: "RESCAN_VERIFIED";
      observation: AutoPilotObservation;
      at: string;
    }
  | {
      type: "CHECKPOINT_SAVED";
      checkpoint: AutoPilotCheckpoint;
      purpose: "NAVIGATION" | "RECOVERY" | "PAUSE";
      at: string;
    }
  | { type: "NAVIGATION_DISPATCHED"; at: string }
  | {
      type: "NAVIGATION_VERIFIED";
      before: AutoPilotObservation;
      after: AutoPilotObservation;
      at: string;
    }
  | { type: "PAUSE_REVIEW"; reason: string; at: string }
  | {
      type: "PAUSE_SECURITY";
      checkpoint: SecurityCheckpointKind;
      reason: string;
      at: string;
    }
  | { type: "PAUSE_FINAL"; reason: string; at: string }
  | { type: "FAIL"; reason: string; at: string }
  | { type: "STOP"; reason?: string; at: string };

const sessionStatusSet = new Set<string>(autoPilotSessionStatuses);
const applicationStateSet = new Set<string>(applicationStates);
const securityCheckpointSet = new Set<string>(securityCheckpointKinds);

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function nullableString(value: unknown, name: string): string | null {
  if (value === null) return null;
  return requiredString(value, name);
}

function assertTimestamp(value: string, name: string): void {
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value) || Number.isNaN(Date.parse(value))) {
    throw new Error(`${name} must be an ISO timestamp`);
  }
}

function uniqueStrings(value: unknown, name: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${name} must be an array`);
  const items = value.map((item) => requiredString(item, name));
  if (new Set(items).size !== items.length) {
    throw new Error(`${name} must not contain duplicates`);
  }
  return items;
}

function normalizeResumePair(input: {
  selectedResumeId: unknown;
  selectedResumeSha256: unknown;
}): { selectedResumeId: string | null; selectedResumeSha256: string | null } {
  const selectedResumeId = nullableString(
    input.selectedResumeId,
    "selectedResumeId",
  );
  const selectedResumeSha256 = nullableString(
    input.selectedResumeSha256,
    "selectedResumeSha256",
  );
  if ((selectedResumeId === null) !== (selectedResumeSha256 === null)) {
    throw new Error("Résumé identity and digest must be stored together");
  }
  if (
    selectedResumeSha256 !== null &&
    !/^[a-f0-9]{64}$/.test(selectedResumeSha256)
  ) {
    throw new Error("selectedResumeSha256 must be a lowercase SHA-256 digest");
  }
  return { selectedResumeId, selectedResumeSha256 };
}

function stableHash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

export function deriveApplicationIdentity(input: {
  url: string;
  externalJobId?: string | null;
}): string {
  const url = new URL(input.url);
  url.hash = "";
  url.search = "";
  const externalJobId = input.externalJobId?.trim() ?? "";
  const canonical = [
    url.origin.toLocaleLowerCase("en-US"),
    url.pathname.replace(/\/+$/, "") || "/",
    externalJobId,
  ].join("|");
  return `app-${stableHash(canonical)}`;
}

export function createAutoPilotSession(input: {
  sessionId: string;
  applicationId: string;
  applicationIdentity: string;
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
  createdAt: string;
}): AutoPilotSession {
  const resume = normalizeResumePair(input);
  const createdAt = requiredString(input.createdAt, "createdAt");
  assertTimestamp(createdAt, "createdAt");
  return {
    schemaVersion: AUTO_PILOT_SESSION_SCHEMA_VERSION,
    sessionId: requiredString(input.sessionId, "sessionId"),
    applicationId: requiredString(input.applicationId, "applicationId"),
    applicationIdentity: requiredString(
      input.applicationIdentity,
      "applicationIdentity",
    ),
    status: "IDLE",
    lastCheckpointSequence: -1,
    lastCheckpointId: null,
    completedControlIds: [],
    pendingControlIds: [],
    selectedResumeId: resume.selectedResumeId,
    selectedResumeSha256: resume.selectedResumeSha256,
    lastApplicationState: null,
    lastPageId: null,
    lastPageFingerprint: null,
    securityCheckpoint: null,
    pauseReason: null,
    updatedAt: createdAt,
  };
}

export function parseAutoPilotSession(value: unknown): AutoPilotSession {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("AutoPilot session must be an object");
  }
  const candidate = value as Record<string, unknown>;
  if (candidate.schemaVersion !== AUTO_PILOT_SESSION_SCHEMA_VERSION) {
    throw new Error("Unsupported AutoPilot session schema version");
  }
  if (
    typeof candidate.status !== "string" ||
    !sessionStatusSet.has(candidate.status)
  ) {
    throw new Error("AutoPilot session status is invalid");
  }
  if (
    !Number.isSafeInteger(candidate.lastCheckpointSequence) ||
    Number(candidate.lastCheckpointSequence) < -1
  ) {
    throw new Error("lastCheckpointSequence must be an integer of -1 or greater");
  }

  const completedControlIds = uniqueStrings(
    candidate.completedControlIds,
    "completedControlIds",
  );
  const pendingControlIds = uniqueStrings(
    candidate.pendingControlIds,
    "pendingControlIds",
  );
  const completed = new Set(completedControlIds);
  if (pendingControlIds.some((controlId) => completed.has(controlId))) {
    throw new Error("Completed and pending session controls must not overlap");
  }

  const resume = normalizeResumePair({
    selectedResumeId: candidate.selectedResumeId,
    selectedResumeSha256: candidate.selectedResumeSha256,
  });
  const lastApplicationState = candidate.lastApplicationState;
  if (
    lastApplicationState !== null &&
    (typeof lastApplicationState !== "string" ||
      !applicationStateSet.has(lastApplicationState))
  ) {
    throw new Error("lastApplicationState is invalid");
  }
  const securityCheckpoint = candidate.securityCheckpoint;
  if (
    securityCheckpoint !== null &&
    (typeof securityCheckpoint !== "string" ||
      !securityCheckpointSet.has(securityCheckpoint))
  ) {
    throw new Error("securityCheckpoint is invalid");
  }

  const updatedAt = requiredString(candidate.updatedAt, "updatedAt");
  assertTimestamp(updatedAt, "updatedAt");

  return {
    schemaVersion: AUTO_PILOT_SESSION_SCHEMA_VERSION,
    sessionId: requiredString(candidate.sessionId, "sessionId"),
    applicationId: requiredString(candidate.applicationId, "applicationId"),
    applicationIdentity: requiredString(
      candidate.applicationIdentity,
      "applicationIdentity",
    ),
    status: candidate.status as AutoPilotSessionStatus,
    lastCheckpointSequence: Number(candidate.lastCheckpointSequence),
    lastCheckpointId: nullableString(
      candidate.lastCheckpointId,
      "lastCheckpointId",
    ),
    completedControlIds,
    pendingControlIds,
    selectedResumeId: resume.selectedResumeId,
    selectedResumeSha256: resume.selectedResumeSha256,
    lastApplicationState: lastApplicationState as ApplicationState | null,
    lastPageId: nullableString(candidate.lastPageId, "lastPageId"),
    lastPageFingerprint: nullableString(
      candidate.lastPageFingerprint,
      "lastPageFingerprint",
    ),
    securityCheckpoint: securityCheckpoint as SecurityCheckpointKind | null,
    pauseReason: nullableString(candidate.pauseReason, "pauseReason"),
    updatedAt,
  };
}

function withObservation(
  session: AutoPilotSession,
  observation: AutoPilotObservation,
  at: string,
  status: AutoPilotSessionStatus,
): AutoPilotSession {
  if (observation.applicationId !== session.applicationId) {
    return {
      ...session,
      status: "PAUSED_ERROR",
      pauseReason: "Observed page belongs to another application",
      updatedAt: at,
    };
  }
  if (observation.securityCheckpoint) {
    return {
      ...session,
      status: "PAUSED_SECURITY",
      securityCheckpoint: observation.securityCheckpoint,
      pauseReason: "Browser security checkpoint requires owner action",
      lastApplicationState: observation.state,
      lastPageId: observation.pageId,
      lastPageFingerprint: observation.pageFingerprint,
      updatedAt: at,
    };
  }
  if (observation.isFinalSubmissionStep || observation.state === "SUBMISSION") {
    return {
      ...session,
      status: "PAUSED_FINAL",
      securityCheckpoint: null,
      pauseReason: "Final employer submission requires owner action",
      lastApplicationState: observation.state,
      lastPageId: observation.pageId,
      lastPageFingerprint: observation.pageFingerprint,
      updatedAt: at,
    };
  }
  if (observation.validationErrorCount > 0) {
    return {
      ...session,
      status: "PAUSED_REVIEW",
      securityCheckpoint: null,
      pauseReason: "Current page contains validation errors",
      lastApplicationState: observation.state,
      lastPageId: observation.pageId,
      lastPageFingerprint: observation.pageFingerprint,
      updatedAt: at,
    };
  }
  return {
    ...session,
    status,
    securityCheckpoint: null,
    pauseReason: null,
    lastApplicationState: observation.state,
    lastPageId: observation.pageId,
    lastPageFingerprint: observation.pageFingerprint,
    updatedAt: at,
  };
}

export function reduceAutoPilotSession(
  session: AutoPilotSession,
  action: AutoPilotSessionAction,
): AutoPilotSession {
  const current = parseAutoPilotSession(session);
  assertTimestamp(action.at, "action.at");

  switch (action.type) {
    case "START":
      if (current.status !== "IDLE") {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: "AutoPilot session can only start from IDLE",
          updatedAt: action.at,
        };
      }
      return withObservation(current, action.observation, action.at, "RUNNING");

    case "FILL_VERIFIED": {
      if (current.status !== "RUNNING") {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: "Verified fill arrived while AutoPilot was not running",
          updatedAt: action.at,
        };
      }
      const controlId = requiredString(action.controlId, "controlId");
      const completed = new Set(current.completedControlIds);
      completed.add(controlId);
      const pending = [...new Set(action.pendingControlIds)].filter(
        (item) => !completed.has(item),
      );
      return parseAutoPilotSession({
        ...current,
        status: "WAITING_RESCAN",
        completedControlIds: [...completed],
        pendingControlIds: pending,
        updatedAt: action.at,
      });
    }

    case "RESCAN_VERIFIED":
      if (current.status !== "WAITING_RESCAN") {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: "Unexpected verified rescan",
          updatedAt: action.at,
        };
      }
      return withObservation(current, action.observation, action.at, "RUNNING");

    case "CHECKPOINT_SAVED": {
      const checkpoint = parseAutoPilotCheckpoint(action.checkpoint);
      if (checkpoint.applicationId !== current.applicationId) {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: "Saved checkpoint belongs to another application",
          updatedAt: action.at,
        };
      }
      const expectedSequence = current.lastCheckpointSequence + 1;
      const isSameAcknowledgement =
        checkpoint.sequence === current.lastCheckpointSequence &&
        checkpoint.checkpointId === current.lastCheckpointId;
      if (!isSameAcknowledgement && checkpoint.sequence !== expectedSequence) {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: "Checkpoint acknowledgement sequence is not monotonic",
          updatedAt: action.at,
        };
      }
      return {
        ...current,
        status:
          action.purpose === "NAVIGATION" && current.status === "RUNNING"
            ? "WAITING_NAVIGATION"
            : current.status,
        lastCheckpointSequence: Math.max(
          current.lastCheckpointSequence,
          checkpoint.sequence,
        ),
        lastCheckpointId: checkpoint.checkpointId,
        updatedAt: action.at,
      };
    }

    case "NAVIGATION_DISPATCHED":
      if (current.status !== "WAITING_NAVIGATION") {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: "Navigation was dispatched without a saved checkpoint",
          updatedAt: action.at,
        };
      }
      return { ...current, status: "WAITING_RESCAN", updatedAt: action.at };

    case "NAVIGATION_VERIFIED": {
      if (current.status !== "WAITING_RESCAN") {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: "Navigation verification arrived in an invalid state",
          updatedAt: action.at,
        };
      }
      const verification = verifyNavigationAction(action.before, action.after);
      if (!verification.success) {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason: verification.reason,
          updatedAt: action.at,
        };
      }
      return withObservation(current, action.after, action.at, "RUNNING");
    }

    case "PAUSE_REVIEW":
      return {
        ...current,
        status: "PAUSED_REVIEW",
        pauseReason: requiredString(action.reason, "reason"),
        updatedAt: action.at,
      };

    case "PAUSE_SECURITY":
      return {
        ...current,
        status: "PAUSED_SECURITY",
        securityCheckpoint: action.checkpoint,
        pauseReason: requiredString(action.reason, "reason"),
        updatedAt: action.at,
      };

    case "PAUSE_FINAL":
      return {
        ...current,
        status: "PAUSED_FINAL",
        pauseReason: requiredString(action.reason, "reason"),
        updatedAt: action.at,
      };

    case "FAIL":
      return {
        ...current,
        status: "PAUSED_ERROR",
        pauseReason: requiredString(action.reason, "reason"),
        updatedAt: action.at,
      };

    case "STOP":
      return {
        ...current,
        status: "STOPPED",
        pauseReason: action.reason?.trim() || null,
        updatedAt: action.at,
      };
  }
}

export function prepareSessionCheckpoint(input: {
  session: AutoPilotSession;
  checkpointId: string;
  observation: AutoPilotObservation;
  createdAt: string;
}): AutoPilotCheckpoint {
  const session = parseAutoPilotSession(input.session);
  if (input.observation.applicationId !== session.applicationId) {
    throw new Error("Cannot checkpoint a different application");
  }
  return createAutoPilotCheckpoint({
    checkpointId: input.checkpointId,
    observation: input.observation,
    sequence: session.lastCheckpointSequence + 1,
    completedControlIds: session.completedControlIds,
    pendingControlIds: session.pendingControlIds,
    selectedResumeId: session.selectedResumeId,
    selectedResumeSha256: session.selectedResumeSha256,
    createdAt: input.createdAt,
  });
}

export function restoreSessionFromCheckpoint(input: {
  session: AutoPilotSession;
  checkpoint: AutoPilotCheckpoint;
  observation: AutoPilotObservation;
  at: string;
}): AutoPilotSession {
  const session = parseAutoPilotSession(input.session);
  const checkpoint = parseAutoPilotCheckpoint(input.checkpoint);
  assertTimestamp(input.at, "at");
  const resume = canResumeFromCheckpoint(checkpoint, input.observation);
  if (
    checkpoint.applicationId !== session.applicationId ||
    input.observation.applicationId !== session.applicationId ||
    !resume.resumable
  ) {
    return {
      ...session,
      status: "PAUSED_ERROR",
      pauseReason: resume.reason,
      updatedAt: input.at,
    };
  }
  const restored = {
    ...session,
    status: "RUNNING" as const,
    lastCheckpointSequence: checkpoint.sequence,
    lastCheckpointId: checkpoint.checkpointId,
    completedControlIds: [...checkpoint.completedControlIds],
    pendingControlIds: [...checkpoint.pendingControlIds],
    selectedResumeId: checkpoint.selectedResumeId,
    selectedResumeSha256: checkpoint.selectedResumeSha256,
    updatedAt: input.at,
  };
  return withObservation(restored, input.observation, input.at, "RUNNING");
}
