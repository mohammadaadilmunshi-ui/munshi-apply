import type {
  ApplicationPage,
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

async function send(request: ExtensionRequest): Promise<unknown> {
  const response = (await chrome.runtime.sendMessage(
    request,
  )) as ExtensionResponse;
  if (!response.ok) throw new Error(response.error);
  return response.data;
}

export async function getActivePage(): Promise<ApplicationPage | null> {
  return (await send({ type: "GET_ACTIVE_PAGE" })) as ApplicationPage | null;
}

export async function getProfile(): Promise<MasterProfile | null> {
  return (await send({ type: "GET_PROFILE" })) as MasterProfile | null;
}

export async function saveProfile(profile: MasterProfile): Promise<void> {
  await send({ type: "SAVE_PROFILE", payload: profile });
}

export async function getHealth(): Promise<ExtensionRuntimeHealth> {
  return (await send({ type: "PING" })) as ExtensionRuntimeHealth;
}

export async function getNativeHealth(): Promise<NativeRuntimeHealth> {
  return (await send({ type: "NATIVE_HEALTH" })) as NativeRuntimeHealth;
}
