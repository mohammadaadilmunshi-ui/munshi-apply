import {
  ApplicationPageSchema,
  FillPlanSchema,
  MasterProfileSchema,
  type ApplicationPage,
  type ExtensionRequest,
  type ExtensionResponse,
} from "@munshi-apply/contracts";
import {
  clearPagesForTab,
  getLatestPage,
  getPage,
  getPagesForTab,
  getProfile,
  savePage,
  saveProfile,
} from "../storage/vault";
import { getNativeHealth } from "../messaging/native";
import {
  getCloudConnection,
  isCloudEncryptionReady,
  publishApplicationSnapshot,
  synchronizeProfile,
} from "../storage/cloud";

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
    const activePage = await getMergedPageForTab(tab.id);
    if (activePage) return activePage;
  }
  return getLatestPage();
}

async function getMergedPageForTab(
  tabId: number,
): Promise<ApplicationPage | null> {
  const pages = await getPagesForTab(tabId);
  if (pages.length === 0) return null;
  const topLevel = pages.find((page) => page.frameId === 0);
  const base = topLevel ?? pages.at(0);
  if (!base) return null;
  const controls = pages.flatMap((page) => page.controls);
  const controlIds = new Set(controls.map((control) => control.controlId));
  return {
    ...base,
    controls,
    questions: pages
      .flatMap((page) => page.questions)
      .filter((question) => controlIds.has(question.controlId)),
    observedAt:
      pages
        .map((page) => page.observedAt)
        .sort((left, right) => right.localeCompare(left))[0] ?? base.observedAt,
  };
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

async function applyFillPlan(payload: unknown): Promise<unknown> {
  const plan = FillPlanSchema.parse(payload);
  const page = await getActivePage();
  if (!page || typeof page !== "object" || !("pageId" in page)) {
    throw new Error("No active application page is available");
  }
  if (page.pageId !== plan.pageId) {
    throw new Error("The active application changed; refresh before filling");
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) throw new Error("No active application tab found");

  const frameIds = new Set(plan.instructions.map((item) => item.frameId));
  const results: unknown[] = [];
  for (const frameId of frameIds) {
    const instructions = plan.instructions.filter(
      (instruction) => instruction.frameId === frameId,
    );
    const response = await chrome.tabs.sendMessage(
      tab.id,
      { type: "APPLY_FILL_INSTRUCTIONS", instructions },
      { frameId },
    );
    if (response && typeof response === "object" && "results" in response) {
      results.push(...(response.results as unknown[]));
    }
  }
  return { pageId: plan.pageId, results };
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
      case "GET_PROFILE": {
        const localProfile = await getProfile();
        const connection = await getCloudConnection();
        if (localProfile && connection && (await isCloudEncryptionReady())) {
          try {
            const synchronized = await synchronizeProfile(
              connection,
              localProfile,
            );
            await saveProfile(synchronized);
            return { ok: true, data: synchronized };
          } catch {
            // Local-first operation continues when cloud is temporarily unavailable.
          }
        }
        return { ok: true, data: localProfile };
      }
      case "SAVE_PROFILE":
        {
          const parsed = MasterProfileSchema.parse(request.payload);
          await saveProfile(parsed);
          const connection = await getCloudConnection();
          if (connection && (await isCloudEncryptionReady())) {
            await synchronizeProfile(connection, parsed);
          }
        }
        return { ok: true };
      case "APPLY_FILL_PLAN":
        return { ok: true, data: await applyFillPlan(request.payload) };
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
        if (frameId === 0) {
          const previousTopLevel = await getPage(tabId, 0);
          if (
            previousTopLevel &&
            previousTopLevel.documentId !== page.documentId
          ) {
            await clearPagesForTab(tabId);
          }
        }
        await savePage(page);
        const mergedPage = await getMergedPageForTab(tabId);
        const connection = await getCloudConnection();
        if (mergedPage && connection && (await isCloudEncryptionReady())) {
          try {
            await publishApplicationSnapshot(connection, mergedPage);
          } catch {
            // Page discovery remains local-first and retries on the next scan.
          }
        }
        try {
          await chrome.runtime.sendMessage({
            type: "ACTIVE_PAGE_UPDATED",
            payload: mergedPage ?? page,
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
