export {};

const REQUEST_TYPE = "MUNSHI_SECURITY_HANDOFF_REQUEST";
const RESPONSE_TYPE = "MUNSHI_SECURITY_HANDOFF_RESPONSE";
const PORT_NAME = "munshi-security-handoff";
const TRUSTED_ORIGINS = new Set([
  "https://munshi.systems",
  "http://localhost:3000",
  "http://127.0.0.1:3000",
]);

type WorkspaceRequest = {
  type: typeof REQUEST_TYPE;
  requestId: string;
  action: "FOCUS" | "RECHECK";
  tabId: number;
  pageId: string;
  expectedOrigin: string;
};

type PortResponse = {
  requestId?: string;
  ok?: boolean;
  action?: "FOCUS" | "RECHECK";
  resumePayload?: {
    preflight: unknown;
    fillInstructions: unknown[];
  };
  error?: string;
};

function isWorkspaceRequest(value: unknown): value is WorkspaceRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Partial<WorkspaceRequest>;
  return (
    candidate.type === REQUEST_TYPE &&
    typeof candidate.requestId === "string" &&
    candidate.requestId.length >= 8 &&
    (candidate.action === "FOCUS" || candidate.action === "RECHECK") &&
    Number.isSafeInteger(candidate.tabId) &&
    Number(candidate.tabId) >= 0 &&
    typeof candidate.pageId === "string" &&
    candidate.pageId.length >= 8 &&
    typeof candidate.expectedOrigin === "string" &&
    candidate.expectedOrigin.startsWith("https://")
  );
}

function postSafeResponse(
  requestId: string,
  payload: Record<string, unknown>,
): void {
  window.postMessage(
    {
      type: RESPONSE_TYPE,
      requestId,
      ...payload,
    },
    window.location.origin,
  );
}

async function finishRecheck(
  request: WorkspaceRequest,
  response: PortResponse,
): Promise<void> {
  if (!response.resumePayload) {
    throw new Error("Chromium did not return a guarded resume plan");
  }

  const pageResponse = (await chrome.runtime.sendMessage({
    type: "GET_ACTIVE_PAGE",
  })) as { ok?: boolean; data?: unknown; error?: string } | undefined;
  if (
    !pageResponse?.ok ||
    !pageResponse.data ||
    typeof pageResponse.data !== "object"
  ) {
    throw new Error(
      pageResponse?.error || "Chromium could not re-scan the application",
    );
  }
  const page = pageResponse.data as {
    pageId?: unknown;
    tabId?: unknown;
    url?: unknown;
    securityCheckpoint?: unknown;
  };
  if (page.pageId !== request.pageId || page.tabId !== request.tabId) {
    throw new Error(
      "The active Chromium application changed during verification",
    );
  }
  let activeOrigin = "";
  try {
    activeOrigin = new URL(String(page.url ?? "")).origin;
  } catch {
    throw new Error("The active Chromium application URL is invalid");
  }
  if (activeOrigin !== request.expectedOrigin) {
    throw new Error(
      "The active Chromium application no longer matches the saved checkpoint",
    );
  }
  if (page.securityCheckpoint) {
    postSafeResponse(request.requestId, {
      ok: true,
      action: "RECHECK",
      status: "STILL_BLOCKED",
    });
    return;
  }

  const resumeResponse = (await chrome.runtime.sendMessage({
    type: "AUTOPILOT_RESUME",
    payload: response.resumePayload,
  })) as { ok?: boolean; data?: unknown; error?: string } | undefined;
  if (!resumeResponse?.ok) {
    throw new Error(
      resumeResponse?.error || "MUNSHI could not resume the application",
    );
  }
  const status =
    resumeResponse.data && typeof resumeResponse.data === "object"
      ? (resumeResponse.data as { session?: { status?: unknown } }).session
          ?.status
      : undefined;
  postSafeResponse(request.requestId, {
    ok: true,
    action: "RECHECK",
    status: status === "PAUSED_SECURITY" ? "STILL_BLOCKED" : "RESUMED",
  });
}

function handleWorkspaceRequest(request: WorkspaceRequest): void {
  const port = chrome.runtime.connect({ name: PORT_NAME });
  let settled = false;
  const finish = () => {
    if (!settled) {
      settled = true;
      try {
        port.disconnect();
      } catch {
        // The service worker can close the port first during an extension reload.
      }
    }
  };

  const timeout = window.setTimeout(() => {
    if (settled) return;
    postSafeResponse(request.requestId, {
      ok: false,
      error: "Chromium verification handoff timed out",
    });
    finish();
  }, 5_000);

  port.onMessage.addListener((response: PortResponse) => {
    if (settled || response.requestId !== request.requestId) return;
    window.clearTimeout(timeout);
    if (!response.ok) {
      postSafeResponse(request.requestId, {
        ok: false,
        error: response.error || "Chromium verification handoff failed",
      });
      finish();
      return;
    }
    if (request.action === "FOCUS") {
      postSafeResponse(request.requestId, {
        ok: true,
        action: "FOCUS",
        status: "FOCUSED",
      });
      finish();
      return;
    }
    void finishRecheck(request, response)
      .catch((error) => {
        postSafeResponse(request.requestId, {
          ok: false,
          error:
            error instanceof Error ? error.message : "Chromium re-check failed",
        });
      })
      .finally(finish);
  });

  port.onDisconnect.addListener(() => {
    if (settled) return;
    window.clearTimeout(timeout);
    postSafeResponse(request.requestId, {
      ok: false,
      error:
        chrome.runtime.lastError?.message ||
        "Chromium verification bridge disconnected",
    });
    settled = true;
  });

  port.postMessage(request);
}

if (window.top === window && TRUSTED_ORIGINS.has(window.location.origin)) {
  window.addEventListener("message", (event: MessageEvent<unknown>) => {
    if (
      event.source !== window ||
      event.origin !== window.location.origin ||
      !TRUSTED_ORIGINS.has(event.origin) ||
      !isWorkspaceRequest(event.data)
    ) {
      return;
    }
    handleWorkspaceRequest(event.data);
  });
}
