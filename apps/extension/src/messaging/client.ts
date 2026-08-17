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

async function send(
  request: ExtensionRequest | AutoPilotRuntimeRequest,
): Promise<unknown> {
  const response = (await chrome.runtime.sendMessage(
    request,
  )) as ExtensionResponse;
  if (!response.ok) throw new Error(response.error);
  return response.data;
}

async function drainProfileSaveQueue(): Promise<void> {
  let failure: unknown = null;
  let acknowledgement: ProfileSaveAck | null = null;
  try {
    while (queuedProfile) {
      const profile = queuedProfile;
      queuedProfile = null;
      const data = await send({ type: "SAVE_PROFILE", payload: profile });
      acknowledgement = parseProfileSaveAck(data);
    }
  } catch (error) {
    failure = error;
  } finally {
    profileSaveRunning = false;
    const waiters = profileSaveWaiters;
    profileSaveWaiters = [];
    if (failure !== null) {
      for (const waiter of waiters) waiter.reject(failure);
    } else if (acknowledgement !== null) {
      for (const waiter of waiters) waiter.resolve(acknowledgement);
    } else {
      const error = new Error(
        "Profile save completed without an acknowledgement",
      );
      for (const waiter of waiters) waiter.reject(error);
    }
  }
}

export async function getRuntimeHealth(): Promise<ExtensionRuntimeHealth> {
  return (await send({ type: "RUNTIME_HEALTH" })) as ExtensionRuntimeHealth;
}

export async function getNativeHealth(): Promise<NativeRuntimeHealth> {
  return (await send({ type: "NATIVE_HEALTH" })) as NativeRuntimeHealth;
}

export async function getProfile(): Promise<ProfileSnapshot> {
  return parseProfileSnapshot(await send({ type: "GET_PROFILE" }));
}

export async function saveProfile(
  profile: ProfileSnapshot,
): Promise<ProfileSaveAck> {
  queuedProfile = parseProfileSnapshot(profile);
  return new Promise((resolve, reject) => {
    profileSaveWaiters.push({ resolve, reject });
    if (profileSaveRunning) return;
    profileSaveRunning = true;
    void drainProfileSaveQueue();
  });
}

export async function getProfileSyncStatus(): Promise<ProfileSyncStatus> {
  return (await send({ type: "GET_PROFILE_SYNC_STATUS" })) as ProfileSyncStatus;
}

export async function getActivePage(): Promise<ApplicationPage | null> {
  return (await send({ type: "GET_ACTIVE_PAGE" })) as ApplicationPage | null;
}

export async function resolveAnswers(page: ApplicationPage): Promise<FillPlan> {
  return (await send({ type: "RESOLVE_ANSWERS", payload: page })) as FillPlan;
}

export async function fillPage(plan: FillPlan): Promise<FillResult[]> {
  return (await send({ type: "FILL_PAGE", payload: plan })) as FillResult[];
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
  reason = "Owner paused AutoPilot",
): Promise<AutoPilotControllerStatus> {
  return (await send({
    type: "AUTOPILOT_PAUSE",
    payload: { reason },
  })) as AutoPilotControllerStatus;
}

export async function resumeAutoPilot(
  payload: AutoPilotResumePayload,
): Promise<AutoPilotControllerStatus> {
  return (await send({
    type: "AUTOPILOT_RESUME",
    payload,
  })) as AutoPilotControllerStatus;
}

export async function stopAutoPilot(
  reason = "Owner stopped AutoPilot",
): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_STOP",
    payload: { reason },
  })) as AutoPilotControllerStatus | null;
}

export async function requestFilePickerAssist(input: {
  frameId: number;
  controlId: string;
}): Promise<unknown> {
  return send({ type: "AUTOPILOT_ASSIST_FILE", payload: input });
}

export async function beginTeach(input: {
  frameId: number;
  controlId: string;
  applicationId: string;
}): Promise<unknown> {
  return send({ type: "TEACH_BEGIN", payload: input });
}

export async function finishTeach(input: {
  frameId: number;
  sessionId: string;
  applicationId: string;
}): Promise<unknown> {
  return send({ type: "TEACH_FINISH", payload: input });
}

export async function cancelTeach(input: {
  frameId: number;
  sessionId: string;
}): Promise<unknown> {
  return send({ type: "TEACH_CANCEL", payload: input });
}
