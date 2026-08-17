import {
  isEligibleApplicationPage,
  type PreflightGateSummary,
} from "@munshi-apply/application-model";
import {
  ApplicationPageSchema,
  FillPlanSchema,
  type ApplicationPage,
  type ExtensionRequest,
  type ExtensionResponse,
  type FillInstruction,
  type FillResult,
} from "@munshi-apply/contracts";
import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";
import {
  AutoPilotController,
  type AutoPilotResumeInput,
  type AutoPilotStartInput,
} from "./autopilot-controller";
import {
  ensureTabContentRuntime,
  sendWithContentRecovery,
  type ContentRuntimeApi,
} from "./content-runtime";
import {
  augmentWithRememberedJobContext,
  clearJobContext,
  rememberJobContext,
} from "./job-context";
import { mergeApplicationPages } from "./page-merge";
import {
  clearPagesForTab,
  deletePage,
  getPage,
  getPagesForTab,
  savePage,
} from "../storage/vault";
import {
  ensureNativeApplication,
  getLatestNativeApplicationCheckpoint,
  getNativeHealth,
  getPromotedInteractionRecipe,
  markAIDraftUsed,
  recordInteractionRecipeAttempt,
  recordInteractionRecipeOutcome,
  teachInteractionRecipe,
  type InteractionRecipeStrategy,
  saveNativeApplicationCheckpoint,
} from "../messaging/native";
import {
  localProfileSaveAck,
  syncedProfileSaveAck,
} from "../messaging/profile-save-ack";
import {
  getCloudConnection,
  getCloudSnapshot,
  isCloudEncryptionReady,
  publishApplicationSnapshot,
} from "../storage/cloud";
import {
  ProtectedProfileConflictError,
  resolveProtectedProfileConflict,
  synchronizeProtectedProfile,
} from "../storage/profile-sync";
import {
  loadAuthoritativeProfileSnapshot,
  persistAuthoritativeProfileSnapshot,
} from "../storage/profile-authority";
import { migrateLegacyProfileSnapshot } from "../storage/profile-migration";

const supportsSidePanel =
  typeof chrome.sidePanel?.setPanelBehavior === "function";
const AUTO_PILOT_RUNTIME_STORAGE_KEY = "autopilot-runtime-v1";

const contentRuntimeApi: ContentRuntimeApi = {
  sendMessage: async <T>(
    tabId: number,
    message: unknown,
    options: { frameId: number },
  ): Promise<T> =>
    (await chrome.tabs.sendMessage(tabId, message, options)) as T,
  executeScript: async (details) => {
    if (!chrome.scripting?.executeScript) {
      throw new Error("Content runtime recovery is unavailable");
    }
    if (details.target.allFrames === true) {
      return chrome.scripting.executeScript({
        target: { tabId: details.target.tabId, allFrames: true },
        files: details.files,
      });
    }
    return chrome.scripting.executeScript({
      target: {
        tabId: details.target.tabId,
        frameIds: details.target.frameIds ?? [0],
      },
      files: details.files,
    });
  },
};

type AutoPilotStartPayload = Omit<AutoPilotStartInput, "tabId"> & {
  tabId?: number;
};

type AutoPilotRuntimeRequest =
  | { type: "AUTOPILOT_START"; payload: AutoPilotStartPayload }
  | { type: "AUTOPILOT_PAUSE"; payload?: { reason?: string } }
  | { type: "AUTOPILOT_RESUME"; payload: AutoPilotResumeInput }
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

type RuntimeRequest = ExtensionRequest | AutoPilotRuntimeRequest;

let initialized = false;
let profileSyncConflict: {
  keys: string[];
  details: ProtectedProfileConflictError["details"];
  detectedAt: string;
} | null = null;

function runSafely(task: Promise<unknown>): void {
  void task.catch(() => undefined);
}

function rememberProfileConflict(error: ProtectedProfileConflictError): void {
  profileSyncConflict = {
    keys: [...error.keys],
    details: [...error.details],
    detectedAt: new Date().toISOString(),
  };
}

function sameProfileSaveContent(
  left: ProfileSnapshot,
  right: ProfileSnapshot,
): boolean {
  return (
    JSON.stringify({ ...left, updatedAt: "SYNC_ACK" }) ===
    JSON.stringify({ ...right, updatedAt: "SYNC_ACK" })
  );
}

async function getMergedPageForTab(
  tabId: number,
): Promise<ApplicationPage | null> {
  return mergeApplicationPages(await getPagesForTab(tabId));
}

const learnableStrategies = new Set<InteractionRecipeStrategy>([
  "ARIA_COMBOBOX",
  "ARIA_RADIO",
  "ARIA_BOOLEAN",
  "CUSTOM_DATE",
  "CUSTOM_MULTI_SELECT",
]);

async function sendFillInstruction(
  tabId: number,
  instruction: FillInstruction,
): Promise<FillResult[]> {
  const before = await getMergedPageForTab(tabId);
  const control = before?.controls.find(
    (candidate) => candidate.controlId === instruction.controlId,
  );
  const question = before?.questions.find(
    (candidate) => candidate.controlId === instruction.controlId,
  );
  let siteOrigin: string | null = null;
  try {
    siteOrigin = before ? new URL(before.url).origin : null;
  } catch {
    siteOrigin = null;
  }
  let promotedRecipe: Awaited<ReturnType<typeof getPromotedInteractionRecipe>> =
    null;
  if (
    siteOrigin &&
    control?.componentFingerprint &&
    question &&
    !question.sensitive
  ) {
    try {
      promotedRecipe = await getPromotedInteractionRecipe({
        siteOrigin,
        componentFingerprint: control.componentFingerprint,
        semanticType: question.semanticType,
      });
    } catch {
      promotedRecipe = null;
    }
  }

  const preferredRecipes =
    promotedRecipe?.strategy === "TAUGHT_RECIPE" &&
    promotedRecipe.state !== "ROLLED_BACK"
      ? {
          [instruction.controlId]: {
            recipeId: promotedRecipe.recipeId,
            strategy: "TAUGHT_RECIPE" as const,
            actions: promotedRecipe.actions,
            state: promotedRecipe.state,
            version: promotedRecipe.version,
          },
        }
      : {};
  const response = await sendWithContentRecovery<
    { results?: FillResult[] } | undefined
  >(contentRuntimeApi, tabId, instruction.frameId, {
    type: "APPLY_FILL_INSTRUCTIONS",
    instructions: [instruction],
    preferredRecipes,
  });
  const results = response?.results ?? [];

  return Promise.all(
    results.map(async (result) => {
      if (
        promotedRecipe &&
        result.recipeAttempted &&
        result.recipeId === promotedRecipe.recipeId
      ) {
        try {
          const learned = await recordInteractionRecipeOutcome({
            recipeId: promotedRecipe.recipeId,
            attemptId: crypto.randomUUID(),
            applicationId: null,
            success:
              result.status === "FILLED" && result.recipeSucceeded === true,
            verified: true,
            failureReason:
              result.status === "FILLED" && result.recipeSucceeded === true
                ? null
                : result.reason,
          });
          return {
            ...result,
            recipeId: learned.recipeId,
            recipeAttempted: true,
            recipeSucceeded: result.recipeSucceeded === true,
          };
        } catch {
          return result;
        }
      }
      const strategy = result.strategy as
        Exclude<InteractionRecipeStrategy, "TAUGHT_RECIPE"> | undefined;
      if (
        !siteOrigin ||
        !control?.componentFingerprint ||
        !question ||
        question.sensitive ||
        !strategy ||
        !learnableStrategies.has(strategy)
      ) {
        return result;
      }
      const promotedAttempted =
        promotedRecipe?.state === "PROMOTED" &&
        promotedRecipe.strategy === strategy;
      try {
        const learned = await recordInteractionRecipeAttempt({
          attemptId: crypto.randomUUID(),
          applicationId: null,
          siteOrigin,
          componentFingerprint: control.componentFingerprint,
          semanticType: question.semanticType,
          strategy,
          success: result.status === "FILLED",
          verified: true,
          failureReason: result.status === "FILLED" ? null : result.reason,
        });
        return {
          ...result,
          recipeId: promotedRecipe?.recipeId ?? learned.recipeId,
          recipeAttempted: promotedAttempted,
          recipeSucceeded: promotedAttempted
            ? result.status === "FILLED"
            : undefined,
        };
      } catch {
        return result;
      }
    }),
  );
}

async function sendNavigationAction(
  tabId: number,
  frameId: number,
  controlId: string,
): Promise<{
  status: "NAVIGATED" | "REFUSED" | "FAILED";
  reason: string;
}> {
  const response = await sendWithContentRecovery<
    | {
        result?: {
          status: "NAVIGATED" | "REFUSED" | "FAILED";
          reason: string;
        };
      }
    | undefined
  >(contentRuntimeApi, tabId, frameId, {
    type: "APPLY_NAVIGATION_ACTION",
    controlId,
  });
  if (!response?.result) {
    return {
      status: "FAILED",
      reason: "Navigation content script returned no verification result",
    };
  }
  return response.result;
}

async function activeHttpTab(): Promise<chrome.tabs.Tab> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined || !/^https?:\/\//.test(tab.url ?? "")) {
    throw new Error("No active browser application tab found");
  }
  return tab;
}

async function beginTeach(
  frameId: number,
  controlId: string,
): Promise<unknown> {
  const tab = await activeHttpTab();
  await ensureTabContentRuntime(contentRuntimeApi, tab.id!);
  const sessionId = `teach-${crypto.randomUUID()}`;
  const response = await sendWithContentRecovery<
    { result?: unknown; error?: string } | undefined
  >(contentRuntimeApi, tab.id!, frameId, {
    type: "TEACH_BEGIN",
    sessionId,
    controlId,
  });
  if (response?.error) throw new Error(response.error);
  if (!response?.result)
    throw new Error("Teach MUNSHI did not start in the employer page");
  return response.result;
}

async function finishTeach(
  frameId: number,
  sessionId: string,
  applicationId: string,
): Promise<unknown> {
  const tab = await activeHttpTab();
  const response = await sendWithContentRecovery<
    | {
        result?: {
          sessionId: string;
          controlId: string;
          componentFingerprint: string;
          changed: boolean;
          reusable: boolean;
          actions: unknown[];
          eventTypes: string[];
          startedAt: string;
          finishedAt: string;
          eventSequence?: { type: string; target: string; atMs: number }[];
          beforeState?: Record<string, unknown>;
          afterState?: Record<string, unknown>;
          quality?: {
            score: number;
            reasons: string[];
            valueCommitted: boolean;
          };
        };
        error?: string;
      }
    | undefined
  >(contentRuntimeApi, tab.id!, frameId, {
    type: "TEACH_FINISH",
    sessionId,
  });
  if (response?.error) throw new Error(response.error);
  const capture = response?.result;
  if (!capture)
    throw new Error("Teach MUNSHI returned no demonstration capture");
  if (!capture.reusable || (capture.quality?.score ?? 0) < 0.8)
    return { ...capture, recipe: null };

  const page = await getMergedPageForTab(tab.id!);
  if (!page)
    throw new Error(
      "Application page changed before the demonstration was saved",
    );
  const control = page.controls.find(
    (item) => item.controlId === capture.controlId,
  );
  const question = page.questions.find(
    (item) => item.controlId === capture.controlId,
  );
  if (!control || !control.componentFingerprint) {
    throw new Error(
      "The demonstrated control changed before its recipe could be saved",
    );
  }
  await ensureNativeApplication(applicationId, page.observedAt);
  const recipe = await teachInteractionRecipe({
    attemptId: `demo-${crypto.randomUUID()}`,
    applicationId,
    siteOrigin: new URL(page.url).origin,
    componentFingerprint: control.componentFingerprint,
    semanticType: question?.semanticType ?? "UNKNOWN",
    actions: capture.actions,
  });
  return { ...capture, recipe };
}

async function cancelTeach(
  frameId: number,
  sessionId: string,
): Promise<unknown> {
  const tab = await activeHttpTab();
  const response = await sendWithContentRecovery<
    { result?: unknown } | undefined
  >(contentRuntimeApi, tab.id!, frameId, { type: "TEACH_CANCEL", sessionId });
  return response?.result ?? { cancelled: false };
}

async function sendFilePickerAssist(
  tabId: number,
  frameId: number,
  controlId: string,
): Promise<unknown> {
  const response = await sendWithContentRecovery<
    { result?: unknown } | undefined
  >(contentRuntimeApi, tabId, frameId, {
    type: "APPLY_FILE_PICKER_ASSIST",
    controlId,
  });
  if (!response?.result) {
    throw new Error("File-picker handoff returned no verification result");
  }
  return response.result;
}

const autoPilotController = new AutoPilotController({
  loadRuntime: async () => {
    const stored = await chrome.storage.session.get(
      AUTO_PILOT_RUNTIME_STORAGE_KEY,
    );
    return stored[AUTO_PILOT_RUNTIME_STORAGE_KEY] ?? null;
  },
  saveRuntime: async (state) => {
    if (state === null) {
      await chrome.storage.session.remove(AUTO_PILOT_RUNTIME_STORAGE_KEY);
      return;
    }
    await chrome.storage.session.set({
      [AUTO_PILOT_RUNTIME_STORAGE_KEY]: state,
    });
  },
  getPage: getMergedPageForTab,
  fill: sendFillInstruction,
  navigate: sendNavigationAction,
  ensureApplication: ensureNativeApplication,
  saveCheckpoint: saveNativeApplicationCheckpoint,
  getLatestCheckpoint: getLatestNativeApplicationCheckpoint,
  markDraftUsed: async (draftId) => {
    await markAIDraftUsed(draftId);
  },
  scheduleTimeout: (delayMilliseconds, callback) => {
    setTimeout(callback, delayMilliseconds);
  },
});

async function initialize(): Promise<void> {
  if (!initialized) {
    initialized = true;
    try {
      await autoPilotController.recover();
    } catch {
      // Runtime recovery is fail-closed inside the controller. The side panel can
      // still open for diagnostics if native messaging is temporarily unavailable.
    }
  }
  if (supportsSidePanel) {
    try {
      await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
    } catch {
      // Side-panel behavior is non-critical. Avoid leaving an unhandled service-worker rejection.
    }
  }
}

if (chrome.webNavigation?.onCommitted) {
  chrome.webNavigation.onCommitted.addListener((details) => {
    if (details.tabId < 0) return;
    runSafely(
      details.frameId === 0
        ? clearPagesForTab(details.tabId)
        : deletePage(details.tabId, details.frameId),
    );
  });
}

chrome.tabs.onRemoved.addListener((tabId) => {
  runSafely(clearJobContext(tabId));
});

if (!supportsSidePanel) {
  chrome.action.onClicked.addListener(() => {
    runSafely(
      chrome.tabs.create({
        url: chrome.runtime.getURL("sidepanel/index.html"),
      }),
    );
  });
}

chrome.runtime.onInstalled.addListener(() => {
  runSafely(initialize());
});

chrome.runtime.onStartup.addListener(() => {
  runSafely(initialize());
});

runSafely(initialize());

async function getActivePage(): Promise<unknown> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined || !/^https?:\/\//.test(tab.url ?? "")) return null;
  await ensureTabContentRuntime(contentRuntimeApi, tab.id);
  const activePage = await getMergedPageForTab(tab.id);
  if (!activePage || !isEligibleApplicationPage(activePage)) return null;
  return augmentWithRememberedJobContext(tab.id, activePage);
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
    const response = await sendWithContentRecovery<{ results?: unknown[] }>(
      contentRuntimeApi,
      tab.id,
      frameId,
      { type: "APPLY_FILL_INSTRUCTIONS", instructions },
    );
    if (response && typeof response === "object" && "results" in response) {
      results.push(...(response.results as unknown[]));
    }
  }
  return { pageId: plan.pageId, results };
}

async function autoPilotStart(
  payload: AutoPilotStartPayload,
): Promise<unknown> {
  const tabId =
    payload.tabId ??
    (await chrome.tabs.query({ active: true, currentWindow: true }))[0]?.id;
  if (tabId === undefined) {
    throw new Error("No active application tab found");
  }
  await ensureTabContentRuntime(contentRuntimeApi, tabId);
  const input: AutoPilotStartInput = {
    tabId,
    applicationId: payload.applicationId,
    preflight: payload.preflight as PreflightGateSummary,
    fillInstructions: payload.fillInstructions,
    selectedResumeId: payload.selectedResumeId,
    selectedResumeSha256: payload.selectedResumeSha256,
  };
  return autoPilotController.start(input);
}

async function routeMessage(
  request: RuntimeRequest,
  sender: chrome.runtime.MessageSender,
): Promise<ExtensionResponse> {
  try {
    switch (request.type) {
      case "PING":
        return { ok: true, data: await extensionHealth() };
      case "NATIVE_HEALTH":
        return { ok: true, data: await getNativeHealth() };
      case "GET_PROFILE": {
        let localProfile = await loadAuthoritativeProfileSnapshot();
        if (localProfile) {
          const migration = migrateLegacyProfileSnapshot(localProfile);
          localProfile = migration.snapshot;
          if (migration.migrated) {
            await persistAuthoritativeProfileSnapshot(localProfile);
          }
        }
        const connection = await getCloudConnection();
        if (connection && (await isCloudEncryptionReady())) {
          try {
            if (localProfile) {
              localProfile = await synchronizeProtectedProfile(
                connection,
                localProfile,
              );
            } else {
              localProfile = (await getCloudSnapshot(connection)).profile;
            }
            if (localProfile) {
              await persistAuthoritativeProfileSnapshot(localProfile);
            }
            profileSyncConflict = null;
          } catch (error) {
            if (error instanceof ProtectedProfileConflictError) {
              rememberProfileConflict(error);
            }
            // Local-first operation continues when cloud is unavailable or review is required.
          }
        }
        return { ok: true, data: localProfile };
      }
      case "GET_PROFILE_SYNC_STATUS":
        return { ok: true, data: { conflict: profileSyncConflict } };
      case "RESOLVE_PROFILE_SYNC_CONFLICT": {
        const localProfile = await loadAuthoritativeProfileSnapshot();
        if (!localProfile) throw new Error("No local profile is available");
        const connection = await getCloudConnection();
        if (!connection || !(await isCloudEncryptionReady())) {
          throw new Error("Encrypted workspace synchronization is unavailable");
        }
        const resolved = await resolveProtectedProfileConflict(
          connection,
          localProfile,
          request.payload.winner,
        );
        await persistAuthoritativeProfileSnapshot(resolved);
        profileSyncConflict = null;
        return { ok: true, data: resolved };
      }
      case "SAVE_PROFILE": {
        const parsed = parseProfileSnapshot(request.payload);
        await persistAuthoritativeProfileSnapshot(parsed);
        const connection = await getCloudConnection();
        const encryptionReady = connection
          ? await isCloudEncryptionReady()
          : false;
        if (!connection || !encryptionReady) {
          return {
            ok: true,
            data: localProfileSaveAck(profileSyncConflict),
          };
        }
        try {
          const synchronized = await synchronizeProtectedProfile(
            connection,
            parsed,
          );
          await persistAuthoritativeProfileSnapshot(synchronized);
          if (!sameProfileSaveContent(synchronized, parsed)) {
            throw new Error(
              "Profile content changed on another device. Refresh before saving again.",
            );
          }
          profileSyncConflict = null;
        } catch (error) {
          if (error instanceof ProtectedProfileConflictError) {
            rememberProfileConflict(error);
            return {
              ok: true,
              data: localProfileSaveAck(profileSyncConflict),
            };
          }
          throw error;
        }
        return { ok: true, data: syncedProfileSaveAck() };
      }
      case "APPLY_FILL_PLAN":
        return { ok: true, data: await applyFillPlan(request.payload) };
      case "GET_ACTIVE_PAGE":
        return { ok: true, data: await getActivePage() };
      case "AUTOPILOT_START":
        return { ok: true, data: await autoPilotStart(request.payload) };
      case "AUTOPILOT_PAUSE":
        return {
          ok: true,
          data: await autoPilotController.pause(request.payload?.reason),
        };
      case "AUTOPILOT_RESUME":
        return {
          ok: true,
          data: await autoPilotController.resume(request.payload),
        };
      case "AUTOPILOT_ASSIST_FILE": {
        const [tab] = await chrome.tabs.query({
          active: true,
          currentWindow: true,
        });
        if (tab?.id === undefined) {
          throw new Error("No active application tab found");
        }
        return {
          ok: true,
          data: await sendFilePickerAssist(
            tab.id,
            request.payload.frameId,
            request.payload.controlId,
          ),
        };
      }
      case "TEACH_BEGIN":
        return {
          ok: true,
          data: await beginTeach(
            request.payload.frameId,
            request.payload.controlId,
          ),
        };
      case "TEACH_FINISH":
        return {
          ok: true,
          data: await finishTeach(
            request.payload.frameId,
            request.payload.sessionId,
            request.payload.applicationId,
          ),
        };
      case "TEACH_CANCEL":
        return {
          ok: true,
          data: await cancelTeach(
            request.payload.frameId,
            request.payload.sessionId,
          ),
        };
      case "AUTOPILOT_STOP":
        return {
          ok: true,
          data: await autoPilotController.stop(request.payload?.reason),
        };
      case "AUTOPILOT_STATUS":
        return { ok: true, data: await autoPilotController.status() };
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
        runSafely(rememberJobContext(tabId, page));
        const previousFrame = await getPage(tabId, frameId);
        if (previousFrame && previousFrame.documentId !== page.documentId) {
          if (frameId === 0) await clearPagesForTab(tabId);
          else await deletePage(tabId, frameId);
        }
        await savePage(page);
        const mergedPage = await getMergedPageForTab(tabId);
        const activePage = mergedPage ?? page;
        const eligible = isEligibleApplicationPage(activePage);
        const contextualPage = eligible
          ? await augmentWithRememberedJobContext(tabId, activePage)
          : activePage;
        const connection = await getCloudConnection();
        if (eligible && connection && (await isCloudEncryptionReady())) {
          try {
            await publishApplicationSnapshot(connection, contextualPage);
          } catch {
            // Page discovery remains local-first and retries on the next scan.
          }
        }
        try {
          await chrome.runtime.sendMessage(
            eligible
              ? { type: "ACTIVE_PAGE_UPDATED", payload: contextualPage }
              : { type: "ACTIVE_PAGE_CLEARED" },
          );
        } catch {
          // The side panel is optional and may be closed while the sensor is active.
        }
        await autoPilotController.onPageSnapshot(tabId, contextualPage);
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
    request: RuntimeRequest,
    sender,
    sendResponse: (response: ExtensionResponse) => void,
  ) => {
    runSafely(
      routeMessage(request, sender).then((response) => {
        try {
          sendResponse(response);
        } catch {
          // The sender can disappear during navigation or extension reload.
        }
      }),
    );
    return true;
  },
);
