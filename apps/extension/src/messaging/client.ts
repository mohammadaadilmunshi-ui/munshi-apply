import type {
  AutoPilotSession,
  PreflightGateSummary,
} from "@munshi-apply/application-model";
import type {
  ApplicationPage,
  FillInstruction,
  FillPlan,
  FillResult,
  ExtensionRequest,
  ExtensionResponse,
} from "@munshi-apply/contracts";
import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";
import {
  parseProfileSaveAck,
  type ProfileSaveAck,
  type ProfileSaveConflict,
  type ProfileSaveConflictDetail,
} from "./profile-save-ack";

export type ExtensionRuntimeHealth = {
  status: string;
  version: string;
  platform: string;
  mobile: boolean;
  capabilities: {
    nativeMessaging: boolean;
    sidePanel: boolean;
  };
};

export type NativeRuntimeHealth = {
  status: string;
  database: string;
  migration_count: number;
  schema_version: string;
  outbox: Record<string, number>;
  protocol_version?: number;
  capabilities?: {
    profile_vault?: boolean;
    application_checkpoints?: boolean;
    interaction_learning?: boolean;
    teach_munshi?: boolean;
    ai_settings?: boolean;
    ai_governance?: boolean;
    ai_draft_lifecycle?: boolean;
    document_evidence_ingestion?: boolean;
    provider_routing?: boolean;
    ollama_fallback?: boolean;
    writing_style_learning?: boolean;
    teach_munshi_state_capture?: boolean;
    account_orchestration?: boolean;
    job_signal_intelligence?: boolean;
    job_signal_identity_binding?: boolean;
    application_analytics?: boolean;
  };
};

export const REQUIRED_NATIVE_PROTOCOL_VERSION = 3;

export type NativeRuntimeCompatibility =
  { compatible: true } | { compatible: false; reason: string };

export function nativeRuntimeCompatibility(
  health: NativeRuntimeHealth,
): NativeRuntimeCompatibility {
  if (health.protocol_version !== REQUIRED_NATIVE_PROTOCOL_VERSION) {
    return {
      compatible: false,
      reason:
        health.protocol_version === undefined
          ? "Installed native companion predates the current protocol."
          : `Installed native protocol ${health.protocol_version}; version ${REQUIRED_NATIVE_PROTOCOL_VERSION} is required.`,
    };
  }
  const requiredCapabilities = [
    "profile_vault",
    "application_checkpoints",
    "interaction_learning",
    "teach_munshi",
    "ai_settings",
    "ai_governance",
    "ai_draft_lifecycle",
    "document_evidence_ingestion",
    "provider_routing",
    "writing_style_learning",
    "account_orchestration",
    "job_signal_intelligence",
    "job_signal_identity_binding",
    "application_analytics",
  ] as const;
  const missing = requiredCapabilities.filter(
    (capability) => health.capabilities?.[capability] !== true,
  );
  return missing.length === 0
    ? { compatible: true }
    : {
        compatible: false,
        reason: `Native companion is missing required capabilities: ${missing.join(", ")}.`,
      };
}

export type AutoPilotControllerStatus = {
  session: AutoPilotSession;
  tabId: number;
  lastUrl: string;
  waitingFor: "FILL" | "NAVIGATION" | null;
  actionDeadlineAt: string | null;
  ownerPauseRequested: boolean;
  ownerPauseReason: string | null;
  pendingDraftUsageId: string | null;
  lastFillResult: FillResult | null;
};

export type AutoPilotStartPayload = {
  applicationId: string;
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
};

export type AutoPilotResumePayload = {
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
};

export type ProfileConflictDetail = ProfileSaveConflictDetail;

export type ProfileSyncStatus = {
  conflict: ProfileSaveConflict | null;
};

type AutoPilotRuntimeRequest =
  | { type: "AUTOPILOT_START"; payload: AutoPilotStartPayload }
  | { type: "AUTOPILOT_PAUSE"; payload?: { reason?: string } }
  | { type: "AUTOPILOT_RESUME"; payload: AutoPilotResumePayload }
  | { type: "AUTOPILOT_STOP"; payload?: { reason?: string } }
  | { type: "AUTOPILOT_STATUS" }
  | {
      type: "AUTOPILOT_ASSIST_FILE";
      payload: { frameId: number; controlId: string };
    }
  | {
      type: "TEACH_BEGIN";
      payload: { frameId: number; controlId: string; applicationId: string };
    }
  | {
      type: "TEACH_FINISH";
      payload: { frameId: number; sessionId: string; applicationId: string };
    }
  | {
      type: "TEACH_CANCEL";
      payload: { frameId: number; sessionId: string };
    };

type ProfileSaveWaiter = {
  resolve: (acknowledgement: ProfileSaveAck) => void;
  reject: (error: unknown) => void;
};

let queuedProfile: ProfileSnapshot | null = null;
let profileSaveRunning = false;
let profileSaveWaiters: ProfileSaveWaiter[] = [];

const transientRuntimeRetryDelays = [120, 320] as const;
const retryableRuntimeRequestTypes = new Set([
  "PING",
  "GET_ACTIVE_PAGE",
  "NATIVE_HEALTH",
]);

function isTransientRuntimeError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return /the user aborted a request|could not establish connection|receiving end does not exist|message port closed|message channel closed|extension context invalidated|context invalidated/i.test(
    message,
  );
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function withTimeout<T>(
  promise: Promise<T>,
  milliseconds: number,
  message: string,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), milliseconds);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

async function send(
  request: ExtensionRequest | AutoPilotRuntimeRequest,
): Promise<unknown> {
  const retryable = retryableRuntimeRequestTypes.has(request.type);
  for (let attempt = 0; ; attempt += 1) {
    try {
      const response = (await chrome.runtime.sendMessage(request)) as
        ExtensionResponse | undefined;
      if (!response) throw new Error("Extension returned no response");
      if (!response.ok) throw new Error(response.error);
      return response.data;
    } catch (error) {
      const delay = transientRuntimeRetryDelays[attempt];
      if (
        !retryable ||
        delay === undefined ||
        !isTransientRuntimeError(error)
      ) {
        throw error;
      }
      await wait(delay);
    }
  }
}

async function drainProfileSaveQueue(): Promise<void> {
  let failure: unknown = null;
  let acknowledgement: ProfileSaveAck | null = null;
  try {
    while (queuedProfile) {
      const profile = queuedProfile;
      queuedProfile = null;
      acknowledgement = parseProfileSaveAck(
        await send({ type: "SAVE_PROFILE", payload: profile }),
      );
    }
  } catch (error) {
    failure = error;
    queuedProfile = null;
  } finally {
    profileSaveRunning = false;
    const waiters = profileSaveWaiters;
    profileSaveWaiters = [];
    for (const waiter of waiters) {
      if (failure) {
        waiter.reject(failure);
      } else if (acknowledgement) {
        waiter.resolve(acknowledgement);
      } else {
        waiter.reject(
          new Error("Profile save completed without acknowledgement"),
        );
      }
    }
    if (queuedProfile && !profileSaveRunning) {
      profileSaveRunning = true;
      void drainProfileSaveQueue();
    }
  }
}

export async function getActivePage(): Promise<ApplicationPage | null> {
  return (await send({ type: "GET_ACTIVE_PAGE" })) as ApplicationPage | null;
}

export async function getProfile(): Promise<ProfileSnapshot | null> {
  const candidate = await send({ type: "GET_PROFILE" });
  return candidate === null ? null : parseProfileSnapshot(candidate);
}

export async function getProfileSyncStatus(): Promise<ProfileSyncStatus> {
  return (await send({ type: "GET_PROFILE_SYNC_STATUS" })) as ProfileSyncStatus;
}

export async function resolveProfileSyncConflict(
  winner: "local" | "remote",
): Promise<ProfileSnapshot> {
  return parseProfileSnapshot(
    await send({
      type: "RESOLVE_PROFILE_SYNC_CONFLICT",
      payload: { winner },
    }),
  );
}

export function saveProfile(profile: ProfileSnapshot): Promise<ProfileSaveAck> {
  queuedProfile = parseProfileSnapshot(profile);
  return new Promise((resolve, reject) => {
    profileSaveWaiters.push({ resolve, reject });
    if (profileSaveRunning) return;
    profileSaveRunning = true;
    void drainProfileSaveQueue();
  });
}

export async function getHealth(): Promise<ExtensionRuntimeHealth> {
  return (await send({ type: "PING" })) as ExtensionRuntimeHealth;
}

export async function getNativeHealth(): Promise<NativeRuntimeHealth> {
  return (await withTimeout(
    send({ type: "NATIVE_HEALTH" }),
    5_000,
    "Native companion health check timed out after 5 seconds",
  )) as NativeRuntimeHealth;
}

export async function applyFillPlan(plan: FillPlan): Promise<FillResult[]> {
  const result = (await send({ type: "APPLY_FILL_PLAN", payload: plan })) as {
    results?: FillResult[];
  };
  return result.results ?? [];
}

export async function getAutoPilotStatus(): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_STATUS",
  })) as AutoPilotControllerStatus | null;
}

export async function startAutoPilot(
  payload: AutoPilotStartPayload,
): Promise<AutoPilotControllerStatus> {
  return (await send({
    type: "AUTOPILOT_START",
    payload,
  })) as AutoPilotControllerStatus;
}

export async function pauseAutoPilot(
  reason = "Paused by owner",
): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_PAUSE",
    payload: { reason },
  })) as AutoPilotControllerStatus | null;
}

export async function resumeAutoPilot(
  payload: AutoPilotResumePayload,
): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_RESUME",
    payload,
  })) as AutoPilotControllerStatus | null;
}

export async function stopAutoPilot(
  reason = "Stopped by owner",
): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_STOP",
    payload: { reason },
  })) as AutoPilotControllerStatus | null;
}

export async function requestFilePickerAssist(
  frameId: number,
  controlId: string,
): Promise<{ status: string; reason: string }> {
  return (await send({
    type: "AUTOPILOT_ASSIST_FILE",
    payload: { frameId, controlId },
  })) as { status: string; reason: string };
}

export type TeachMunshiStart = {
  sessionId: string;
  frameId: number;
  controlId: string;
  label: string;
  componentFingerprint: string;
  startedAt: string;
};

export type TeachMunshiResult = {
  sessionId: string;
  controlId: string;
  resolvedControlId?: string;
  changed: boolean;
  reusable: boolean;
  eventTypes: string[];
  eventSequence?: { type: string; target: string; atMs: number }[];
  beforeState?: Record<string, unknown>;
  afterState?: Record<string, unknown>;
  quality?: { score: number; reasons: string[]; valueCommitted: boolean };
  recipe: null | {
    recipeId: string;
    state: "SHADOW" | "PROMOTED" | "ROLLED_BACK";
    version: number;
    verifiedAttempts?: number;
    verifiedSuccesses?: number;
  };
};

export async function beginTeachMunshi(
  frameId: number,
  controlId: string,
  applicationId: string,
): Promise<TeachMunshiStart> {
  const started = (await send({
    type: "TEACH_BEGIN",
    payload: { frameId, controlId, applicationId },
  })) as Omit<TeachMunshiStart, "frameId">;
  return { ...started, frameId };
}

export async function finishTeachMunshi(
  frameId: number,
  sessionId: string,
  applicationId: string,
): Promise<TeachMunshiResult> {
  return (await send({
    type: "TEACH_FINISH",
    payload: { frameId, sessionId, applicationId },
  })) as TeachMunshiResult;
}

export async function cancelTeachMunshi(
  frameId: number,
  sessionId: string,
): Promise<void> {
  await send({ type: "TEACH_CANCEL", payload: { frameId, sessionId } });
}
