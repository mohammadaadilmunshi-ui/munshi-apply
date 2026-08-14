import type {
  ApplicationPage,
  ExtensionRequest,
  ExtensionResponse,
  MasterProfile,
} from "@munshi-apply/contracts";

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

export async function getHealth(): Promise<{
  status: string;
  version: string;
}> {
  return (await send({ type: "PING" })) as { status: string; version: string };
}
