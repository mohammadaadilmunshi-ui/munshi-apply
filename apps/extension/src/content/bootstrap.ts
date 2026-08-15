import type {
  ExtensionRequest,
  FillInstruction,
} from "@munshi-apply/contracts";
import { applyFillInstructions, assistFilePicker } from "./fill";
import { refreshFileFingerprint } from "./adaptive";
import { applyNavigationAction } from "./navigation";
import { scanDocument, snapshotFingerprint } from "./scanner";

const SCAN_DEBOUNCE_MS = 150;
const MAX_SCAN_DEBOUNCE_MS = 600;
let previousFingerprint = "";
let pending: number | undefined;
let debounceStartedAt = 0;
let scanQueue: Promise<void> = Promise.resolve();

async function publishSnapshot(force = false): Promise<void> {
  const page = scanDocument();
  const fingerprint = snapshotFingerprint(page);
  if (!force && fingerprint === previousFingerprint) return;
  previousFingerprint = fingerprint;
  const request: ExtensionRequest = { type: "PAGE_SNAPSHOT", payload: page };
  try {
    await chrome.runtime.sendMessage(request);
  } catch {
    // The extension may be restarting. The background runtime re-establishes
    // the sensor before the next page read or owner action.
  }
}

function enqueueSnapshot(force: boolean): Promise<void> {
  scanQueue = scanQueue
    .catch(() => undefined)
    .then(() => publishSnapshot(force));
  return scanQueue;
}

function clearPendingScan(): void {
  if (pending !== undefined) window.clearTimeout(pending);
  pending = undefined;
}

function scheduleScan(force = false): void {
  if (force) {
    clearPendingScan();
    debounceStartedAt = 0;
    void enqueueSnapshot(true);
    return;
  }

  const current = Date.now();
  if (debounceStartedAt === 0) debounceStartedAt = current;
  const elapsed = current - debounceStartedAt;
  if (elapsed >= MAX_SCAN_DEBOUNCE_MS) {
    clearPendingScan();
    debounceStartedAt = 0;
    void enqueueSnapshot(false);
    return;
  }

  clearPendingScan();
  pending = window.setTimeout(
    () => {
      pending = undefined;
      debounceStartedAt = 0;
      void enqueueSnapshot(false);
    },
    Math.min(SCAN_DEBOUNCE_MS, MAX_SCAN_DEBOUNCE_MS - elapsed),
  );
}

function wrapHistoryMethod(method: "pushState" | "replaceState"): void {
  const original = history[method].bind(history);
  history[method] = ((...args: Parameters<History["pushState"]>) => {
    original(...args);
    scheduleScan();
  }) as History["pushState"];
}

const observer = new MutationObserver(() => scheduleScan());
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

document.addEventListener("input", () => scheduleScan(), true);
document.addEventListener(
  "change",
  (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement && target.type === "file") {
      void refreshFileFingerprint(target).finally(() => scheduleScan(true));
      return;
    }
    scheduleScan();
  },
  true,
);
document.addEventListener("invalid", () => scheduleScan(true), true);
document.addEventListener("blur", () => scheduleScan(), true);
window.addEventListener("pageshow", () => scheduleScan(true));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") scheduleScan(true);
});
window.addEventListener("popstate", () => scheduleScan());
window.addEventListener("hashchange", () => scheduleScan());
wrapHistoryMethod("pushState");
wrapHistoryMethod("replaceState");
void enqueueSnapshot(false);

chrome.runtime.onMessage.addListener(
  (
    message: {
      type?: string;
      instructions?: FillInstruction[];
      controlId?: string;
    },
    _sender,
    sendResponse,
  ) => {
    if (message.type === "CONTENT_PING") {
      sendResponse({ ok: true });
      return false;
    }
    if (message.type === "CONTENT_SCAN_NOW") {
      void enqueueSnapshot(true)
        .then(() => sendResponse({ ok: true }))
        .catch((error: unknown) =>
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : "Scan failed",
          }),
        );
      return true;
    }
    if (message.type === "APPLY_FILL_INSTRUCTIONS" && message.instructions) {
      void applyFillInstructions(message.instructions)
        .then((results) => {
          sendResponse({ results });
          scheduleScan(true);
        })
        .catch((error: unknown) => {
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
          scheduleScan(true);
        });
      return true;
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
  },
);
