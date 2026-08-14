import {
  ApplicationPageSchema,
  MasterProfileSchema,
  type ExtensionRequest,
  type ExtensionResponse,
} from "@munshi-apply/contracts";
import {
  getLatestPage,
  getPage,
  getProfile,
  savePage,
  saveProfile,
} from "../storage/vault";
import { getNativeHealth } from "../messaging/native";

const supportsSidePanel =
  typeof chrome.sidePanel?.setPanelBehavior === "function";

async function initialize(): Promise<void> {
  if (supportsSidePanel) {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
}

if (!supportsSidePanel) {
  chrome.action.onClicked.addListener(() => {
    void chrome.tabs.create({
      url: chrome.runtime.getURL("sidepanel/index.html"),
    });
  });
}

chrome.runtime.onInstalled.addListener(() => {
  void initialize();
});

chrome.runtime.onStartup.addListener(() => {
  void initialize();
});

async function getActivePage(): Promise<unknown> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id !== undefined && /^https?:\/\//.test(tab.url ?? "")) {
    const activePage = await getPage(tab.id);
    if (activePage) return activePage;
  }
  return getLatestPage();
}

async function extensionHealth(): Promise<unknown> {
  const platform = await chrome.runtime.getPlatformInfo();
  const platformName = String(platform.os);
  const declaredPermissions = chrome.runtime.getManifest().permissions ?? [];
  return {
    status: "healthy",
    version: chrome.runtime.getManifest().version,
    platform: platformName,
    mobile: ["android", "ios"].includes(platformName),
    capabilities: {
      nativeMessaging: declaredPermissions.includes("nativeMessaging"),
      sidePanel: supportsSidePanel,
    },
  };
}

async function routeMessage(
  request: ExtensionRequest,
  sender: chrome.runtime.MessageSender,
): Promise<ExtensionResponse> {
  try {
    switch (request.type) {
      case "PING":
        return { ok: true, data: await extensionHealth() };
      case "NATIVE_HEALTH":
        return { ok: true, data: await getNativeHealth() };
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
