import type {
  ApplicationPage,
  FillPlan,
  FillResult,
  ExtensionRequest,
  ExtensionResponse,
  MasterProfile,
} from "@munshi-apply/contracts";

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

type ProfileSaveWaiter = {
  resolve: () => void;
  reject: (error: unknown) => void;
};

let queuedProfile: MasterProfile | null = null;
let profileSaveRunning = false;
let profileSaveWaiters: ProfileSaveWaiter[] = [];

async function send(request: ExtensionRequest): Promise<unknown> {
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

export async function getProfile(): Promise<MasterProfile | null> {
  return (await send({ type: "GET_PROFILE" })) as MasterProfile | null;
}

export function saveProfile(profile: MasterProfile): Promise<void> {
  queuedProfile = profile;
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
  const result = (await send({
    type: "APPLY_FILL_PLAN",
    payload: plan,
  })) as { results?: FillResult[] };
  return result.results ?? [];
}
