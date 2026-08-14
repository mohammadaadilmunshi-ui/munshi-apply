import type {
  ExtensionRequest,
  FillInstruction,
} from "@munshi-apply/contracts";
import { applyFillInstructions } from "./fill";
import { scanDocument, snapshotFingerprint } from "./scanner";

let previousFingerprint = "";
let pending: number | undefined;

async function publishSnapshot(): Promise<void> {
  const page = scanDocument();
  const fingerprint = snapshotFingerprint(page);
  if (fingerprint === previousFingerprint) return;
  previousFingerprint = fingerprint;
  const request: ExtensionRequest = { type: "PAGE_SNAPSHOT", payload: page };
  try {
    await chrome.runtime.sendMessage(request);
  } catch {
    // The extension may have reloaded while the page remained open.
  }
}

function scheduleScan(): void {
  if (pending !== undefined) window.clearTimeout(pending);
  pending = window.setTimeout(() => {
    pending = undefined;
    void publishSnapshot();
  }, 150);
}

function wrapHistoryMethod(method: "pushState" | "replaceState"): void {
  const original = history[method].bind(history);
  history[method] = ((...args: Parameters<History["pushState"]>) => {
    original(...args);
    scheduleScan();
  }) as History["pushState"];
}

const observer = new MutationObserver(scheduleScan);
observer.observe(document.documentElement, {
  attributes: true,
  childList: true,
  subtree: true,
  attributeFilter: [
    "aria-expanded",
    "aria-hidden",
    "aria-invalid",
    "aria-label",
    "aria-labelledby",
    "aria-required",
    "class",
    "disabled",
    "hidden",
    "name",
    "placeholder",
    "required",
    "style",
  ],
});

document.addEventListener("input", scheduleScan, true);
document.addEventListener("change", scheduleScan, true);
window.addEventListener("popstate", scheduleScan);
window.addEventListener("hashchange", scheduleScan);
wrapHistoryMethod("pushState");
wrapHistoryMethod("replaceState");
void publishSnapshot();

chrome.runtime.onMessage.addListener(
  (
    message: { type?: string; instructions?: FillInstruction[] },
    _sender,
    sendResponse,
  ) => {
    if (message.type !== "APPLY_FILL_INSTRUCTIONS" || !message.instructions) {
      return false;
    }
    sendResponse({ results: applyFillInstructions(message.instructions) });
    scheduleScan();
    return false;
  },
);
