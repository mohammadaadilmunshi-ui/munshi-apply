import {
  ApplicationPageSchema,
  MasterProfileSchema,
  type ExtensionRequest,
  type ExtensionResponse,
} from "@munshi-apply/contracts";
import { getPage, getProfile, savePage, saveProfile } from "../storage/vault";

async function initialize(): Promise<void> {
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
}

chrome.runtime.onInstalled.addListener(() => {
  void initialize();
});

chrome.runtime.onStartup.addListener(() => {
  void initialize();
});

async function getActivePage(): Promise<unknown> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) return null;
  return getPage(tab.id);
}

async function routeMessage(
  request: ExtensionRequest,
  sender: chrome.runtime.MessageSender,
): Promise<ExtensionResponse> {
  try {
    switch (request.type) {
      case "PING":
        return { ok: true, data: { status: "healthy", version: "0.1.0" } };
      case "GET_PROFILE":
        return { ok: true, data: await getProfile() };
      case "SAVE_PROFILE":
        await saveProfile(MasterProfileSchema.parse(request.payload));
        return { ok: true };
      case "GET_ACTIVE_PAGE":
        return { ok: true, data: await getActivePage() };
      case "PAGE_SNAPSHOT": {
        const tabId = sender.tab?.id;
        const frameId = sender.frameId ?? 0;
        if (tabId === undefined) {
          return {
            ok: false,
            error: "Page snapshot did not include a browser tab",
          };
        }
        const page = ApplicationPageSchema.parse({
          ...request.payload,
          tabId,
          frameId,
          documentId: sender.documentId ?? request.payload.documentId,
          controls: request.payload.controls.map((control) => ({
            ...control,
            frameId,
          })),
        });
        await savePage(page);
        try {
          await chrome.runtime.sendMessage({
            type: "ACTIVE_PAGE_UPDATED",
            payload: page,
          });
        } catch {
          // The side panel is optional and may be closed while the sensor is active.
        }
        return { ok: true };
      }
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown extension error";
    return { ok: false, error: message };
  }
}

chrome.runtime.onMessage.addListener(
  (
    request: ExtensionRequest,
    sender,
    sendResponse: (response: ExtensionResponse) => void,
  ) => {
    void routeMessage(request, sender).then(sendResponse);
    return true;
  },
);
