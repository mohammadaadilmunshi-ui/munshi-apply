const PORT_NAME = "munshi-security-handoff";
const AUTO_PILOT_RUNTIME_STORAGE_KEY = "autopilot-runtime-v1";

type HandoffRequest = {
  requestId: string;
  action: "FOCUS" | "RECHECK";
  tabId: number;
  pageId: string;
  expectedOrigin: string;
};

type RuntimeShape = {
  tabId?: unknown;
  preflight?: unknown;
  fillInstructions?: unknown;
  session?: {
    status?: unknown;
    lastPageId?: unknown;
  };
};

function safeOrigin(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.origin : null;
  } catch {
    return null;
  }
}

function validRequest(value: unknown): value is HandoffRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Partial<HandoffRequest>;
  return (
    typeof candidate.requestId === "string" &&
    candidate.requestId.length >= 8 &&
    candidate.requestId.length <= 160 &&
    (candidate.action === "FOCUS" || candidate.action === "RECHECK") &&
    Number.isSafeInteger(candidate.tabId) &&
    Number(candidate.tabId) >= 0 &&
    typeof candidate.pageId === "string" &&
    candidate.pageId.length >= 8 &&
    candidate.pageId.length <= 256 &&
    safeOrigin(candidate.expectedOrigin) === candidate.expectedOrigin
  );
}

async function validatedRuntime(request: HandoffRequest): Promise<{
  runtime: RuntimeShape;
  tab: chrome.tabs.Tab;
}> {
  const tab = await chrome.tabs.get(request.tabId);
  const tabOrigin = safeOrigin(tab.url);
  if (!tab.url || tabOrigin !== request.expectedOrigin) {
    throw new Error("The saved Chromium tab no longer matches this application site");
  }

  const stored = await chrome.storage.session.get(AUTO_PILOT_RUNTIME_STORAGE_KEY);
  const runtime = stored[AUTO_PILOT_RUNTIME_STORAGE_KEY] as RuntimeShape | undefined;
  if (!runtime || runtime.tabId !== request.tabId) {
    throw new Error("The saved AutoPilot session no longer owns this Chromium tab");
  }
  if (runtime.session?.status !== "PAUSED_SECURITY") {
    throw new Error("The AutoPilot session is not paused at a security checkpoint");
  }
  if (
    typeof runtime.session.lastPageId === "string" &&
    runtime.session.lastPageId !== request.pageId
  ) {
    throw new Error("The application page changed after the security checkpoint was created");
  }
  if (!runtime.preflight || !Array.isArray(runtime.fillInstructions)) {
    throw new Error("The paused AutoPilot session is missing its guarded resume plan");
  }
  return { runtime, tab };
}

async function focusTab(tab: chrome.tabs.Tab): Promise<void> {
  if (tab.id === undefined) throw new Error("Chromium application tab is unavailable");
  if (tab.windowId !== undefined) {
    await chrome.windows.update(tab.windowId, { focused: true });
  }
  await chrome.tabs.update(tab.id, { active: true });
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== PORT_NAME) return;

  port.onMessage.addListener((candidate) => {
    void (async () => {
      if (!validRequest(candidate)) {
        throw new Error("Invalid security checkpoint handoff request");
      }
      const request = candidate;
      const { runtime, tab } = await validatedRuntime(request);
      await focusTab(tab);

      if (request.action === "FOCUS") {
        port.postMessage({
          requestId: request.requestId,
          ok: true,
          action: "FOCUS",
        });
        return;
      }

      await chrome.tabs.sendMessage(
        request.tabId,
        { type: "CONTENT_SCAN_NOW" },
        { frameId: 0 },
      );
      port.postMessage({
        requestId: request.requestId,
        ok: true,
        action: "RECHECK",
        resumePayload: {
          preflight: runtime.preflight,
          fillInstructions: runtime.fillInstructions,
        },
      });
    })().catch((error) => {
      try {
        port.postMessage({
          requestId:
            candidate && typeof candidate === "object" && "requestId" in candidate
              ? String(candidate.requestId)
              : "unknown",
          ok: false,
          error: error instanceof Error ? error.message : "Chromium handoff failed",
        });
      } catch {
        // The owner workspace may have navigated away during the handoff.
      }
    });
  });
});
