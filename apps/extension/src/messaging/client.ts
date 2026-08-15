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
};

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

type AutoPilotRuntimeRequest =
  | { type: "AUTOPILOT_START"; payload: AutoPilotStartPayload }
  | { type: "AUTOPILOT_PAUSE"; payload?: { reason?: string } }
  | { type: "AUTOPILOT_RESUME"; payload: AutoPilotResumePayload }
  | { type: "AUTOPILOT_STOP"; payload?: { reason?: string } }
  | { type: "AUTOPILOT_STATUS" }
  | {
      type: "AUTOPILOT_ASSIST_FILE";
      payload: { frameId: number; controlId: string };
    };

type ProfileSaveWaiter = {
  resolve: () => void;
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
  try {
    while (queuedProfile) {
      const profile = queuedProfile;
      queuedProfile = null;
      await send({ type: "SAVE_PROFILE", payload: profile });
    }
  } catch (error) {
    failure = error;
    queuedProfile = null;
  } finally {
    profileSaveRunning = false;
    const waiters = profileSaveWaiters;
    profileSaveWaiters = [];
    for (const waiter of waiters) {
      if (failure) waiter.reject(failure);
      else waiter.resolve();
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

export function saveProfile(profile: ProfileSnapshot): Promise<void> {
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
  return (await send({ type: "NATIVE_HEALTH" })) as NativeRuntimeHealth;
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
