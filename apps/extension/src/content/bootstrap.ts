import type {
  ExtensionRequest,
  ExtensionResponse,
  FillInstruction,
} from "@munshi-apply/contracts";
import {
  applyFillInstructions,
  assistFilePicker,
  type PreferredInteractionRecipe,
} from "./fill";
import {
  beginTeachInteraction,
  cancelTeachInteraction,
  finishTeachInteraction,
} from "./teach";
import { refreshFileFingerprint } from "./adaptive";
import {
  isApplicationRelevantTarget,
  shouldRescanFromMutations,
} from "./mutation-rescan-policy";
import { applyNavigationAction } from "./navigation";
import { automaticScanIntervalMs } from "./scan-pacing";
import { scanDocument, snapshotFingerprint } from "./scanner";
import {
  disposePreviousContentRuntime,
  registerContentRuntime,
} from "./runtime-lifecycle";
import { createSnapshotCoalescer } from "./snapshot-coalescer";
import { createSnapshotRetryController } from "./snapshot-retry";

disposePreviousContentRuntime();

const SCAN_DEBOUNCE_MS = 300;
const MAX_SCAN_DEBOUNCE_MS = 1_500;
let previousFingerprint = "";
let pending: number | undefined;
let pendingForce = false;
let pendingWhenVisible = false;
let debounceStartedAt = 0;
let lastScanStartedAt = 0;
let lastScanDurationMs = 0;
let unchangedScanStreak = 0;
let disposed = false;
const listenerAbortController = new AbortController();
const snapshotRetry = createSnapshotRetryController();

async function publishSnapshot(force = false): Promise<void> {
  if (disposed) return;
  lastScanStartedAt = Date.now();
  const scanStartedAt = performance.now();
  const page = scanDocument();
  lastScanDurationMs = Math.max(0, performance.now() - scanStartedAt);
  const fingerprint = page.pageFingerprint || snapshotFingerprint(page);
  const unchanged =
    previousFingerprint !== "" && fingerprint === previousFingerprint;
  unchangedScanStreak = unchanged ? unchangedScanStreak + 1 : 0;
  if (!force && unchanged) return;
  const request: ExtensionRequest = { type: "PAGE_SNAPSHOT", payload: page };
  const response = (await chrome.runtime.sendMessage(request)) as
    ExtensionResponse | undefined;
  if (!response?.ok) {
    throw new Error(response?.error || "Background rejected page snapshot");
  }
  previousFingerprint = fingerprint;
  snapshotRetry.succeeded();
}

const snapshotCoalescer = createSnapshotCoalescer(publishSnapshot);

function enqueueSnapshot(force: boolean): Promise<void> {
  return snapshotCoalescer.request(force);
}

function runSnapshot(force: boolean): void {
  void enqueueSnapshot(force).catch(() => {
    snapshotRetry.failed(() => runSnapshot(true));
  });
}

function clearPendingScan(): void {
  if (pending !== undefined) window.clearTimeout(pending);
  pending = undefined;
}

function scheduleScan(force = false): void {
  if (disposed) return;
  pendingForce ||= force;

  if (document.visibilityState !== "visible") {
    pendingWhenVisible = true;
    clearPendingScan();
    debounceStartedAt = 0;
    return;
  }

  const current = Date.now();
  if (debounceStartedAt === 0) debounceStartedAt = current;
  const elapsed = current - debounceStartedAt;
  const debounceDelay =
    elapsed >= MAX_SCAN_DEBOUNCE_MS
      ? 0
      : Math.min(SCAN_DEBOUNCE_MS, MAX_SCAN_DEBOUNCE_MS - elapsed);
  const automaticInterval = force
    ? 0
    : automaticScanIntervalMs({
        lastScanDurationMs,
        unchangedScanStreak,
      });
  const throttleDelay =
    lastScanStartedAt === 0
      ? 0
      : Math.max(0, automaticInterval - (current - lastScanStartedAt));

  clearPendingScan();
  pending = window.setTimeout(
    () => {
      pending = undefined;
      debounceStartedAt = 0;
      const forceNext = pendingForce;
      pendingForce = false;
      runSnapshot(forceNext);
    },
    Math.max(debounceDelay, throttleDelay),
  );
}

function wrapHistoryMethod(method: "pushState" | "replaceState"): () => void {
  const original = history[method];
  const wrapped = ((...args: Parameters<History["pushState"]>) => {
    original.apply(history, args);
    scheduleScan();
  }) as History["pushState"];
  try {
    history[method] = wrapped;
  } catch {
    return () => undefined;
  }
  return () => {
    try {
      if (history[method] === wrapped) {
        history[method] = original as History["pushState"];
      }
    } catch {
      // Some applications lock the History object after initialization.
    }
  };
}

let observer: MutationObserver | null = null;
try {
  if (document.documentElement) {
    observer = new MutationObserver((records) => {
      if (shouldRescanFromMutations(records)) scheduleScan();
    });
    observer.observe(document.documentElement, {
      attributes: true,
      childList: true,
      subtree: true,
      attributeFilter: [
        "aria-activedescendant",
        "aria-busy",
        "aria-checked",
        "aria-expanded",
        "aria-hidden",
        "aria-invalid",
        "aria-label",
        "aria-labelledby",
        "aria-required",
        "aria-selected",
        "aria-valuetext",
        "class",
        "data-value",
        "disabled",
        "hidden",
        "name",
        "placeholder",
        "required",
        "style",
      ],
    });
  }
} catch {
  observer = null;
}

const listenerOptions = { signal: listenerAbortController.signal };
const captureListenerOptions = {
  capture: true,
  signal: listenerAbortController.signal,
};

document.addEventListener(
  "change",
  (event) => {
    if (!isApplicationRelevantTarget(event.target)) return;
    const target = event.target;
    if (target instanceof HTMLInputElement && target.type === "file") {
      void refreshFileFingerprint(target)
        .catch(() => undefined)
        .finally(() => scheduleScan(true));
      return;
    }
    scheduleScan();
  },
  captureListenerOptions,
);
document.addEventListener(
  "invalid",
  (event) => {
    if (isApplicationRelevantTarget(event.target)) scheduleScan(true);
  },
  captureListenerOptions,
);
document.addEventListener(
  "blur",
  (event) => {
    if (isApplicationRelevantTarget(event.target)) scheduleScan();
  },
  captureListenerOptions,
);
window.addEventListener("pageshow", () => scheduleScan(true), listenerOptions);
document.addEventListener(
  "visibilitychange",
  () => {
    if (document.visibilityState !== "visible") return;
    const force = pendingForce || pendingWhenVisible;
    pendingForce = false;
    pendingWhenVisible = false;
    scheduleScan(force);
  },
  listenerOptions,
);
window.addEventListener("popstate", () => scheduleScan(), listenerOptions);
window.addEventListener("hashchange", () => scheduleScan(), listenerOptions);
const restorePushState = wrapHistoryMethod("pushState");
const restoreReplaceState = wrapHistoryMethod("replaceState");
scheduleScan(false);

const runtimeMessageListener = (
  message: {
    type?: string;
    instructions?: FillInstruction[];
    preferredRecipes?: Record<string, PreferredInteractionRecipe>;
    controlId?: string;
    sessionId?: string;
  },
  _sender: chrome.runtime.MessageSender,
  sendResponse: (response?: unknown) => void,
): boolean => {
  if (disposed) return false;
  if (message.type === "CONTENT_PING") {
    sendResponse({ ok: true });
    return false;
  }
  if (message.type === "CONTENT_SCAN_NOW") {
    void enqueueSnapshot(true)
      .then(() => sendResponse({ ok: true }))
      .catch((error: unknown) => {
        try {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : "Scan failed",
          });
        } catch {
          // The requesting port may have disappeared during an extension reload.
        }
      });
    return true;
  }
  if (message.type === "APPLY_FILL_INSTRUCTIONS" && message.instructions) {
    void applyFillInstructions(
      message.instructions,
      {},
      message.preferredRecipes ?? {},
    )
      .then((results) => {
        try {
          sendResponse({ results });
        } finally {
          scheduleScan(true);
        }
      })
      .catch((error: unknown) => {
        try {
          sendResponse({
            results: message.instructions!.map((instruction) => ({
              controlId: instruction.controlId,
              status: "FAILED",
              reason:
                error instanceof Error
                  ? error.message
                  : "Guarded fill failed unexpectedly",
            })),
          });
        } finally {
          scheduleScan(true);
        }
      });
    return true;
  }
  if (
    message.type === "TEACH_BEGIN" &&
    message.controlId &&
    message.sessionId
  ) {
    try {
      sendResponse({
        result: beginTeachInteraction(message.sessionId, message.controlId),
      });
    } catch (error) {
      sendResponse({
        error:
          error instanceof Error
            ? error.message
            : "Teach MUNSHI could not start",
      });
    }
    return false;
  }
  if (message.type === "TEACH_FINISH" && message.sessionId) {
    try {
      sendResponse({ result: finishTeachInteraction(message.sessionId) });
    } catch (error) {
      sendResponse({
        error:
          error instanceof Error
            ? error.message
            : "Teach MUNSHI could not finish",
      });
    }
    return false;
  }
  if (message.type === "TEACH_CANCEL" && message.sessionId) {
    sendResponse({ result: cancelTeachInteraction(message.sessionId) });
    return false;
  }
  if (message.type === "APPLY_FILE_PICKER_ASSIST" && message.controlId) {
    sendResponse({ result: assistFilePicker(message.controlId) });
    scheduleScan(true);
    return false;
  }
  if (message.type === "APPLY_NAVIGATION_ACTION" && message.controlId) {
    sendResponse({ result: applyNavigationAction(message.controlId) });
    scheduleScan(true);
    return false;
  }
  return false;
};

chrome.runtime.onMessage.addListener(runtimeMessageListener);

registerContentRuntime(() => {
  disposed = true;
  snapshotCoalescer.dispose();
  snapshotRetry.dispose();
  clearPendingScan();
  pendingForce = false;
  pendingWhenVisible = false;
  debounceStartedAt = 0;
  observer?.disconnect();
  listenerAbortController.abort();
  restorePushState();
  restoreReplaceState();
  try {
    chrome.runtime.onMessage.removeListener(runtimeMessageListener);
  } catch {
    // Reloaded extensions can invalidate the previous Chrome runtime object.
  }
});
