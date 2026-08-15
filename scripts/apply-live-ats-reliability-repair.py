from __future__ import annotations

import json
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


# Desktop-only programmatic reinjection is used to recover MUNSHI's own
# content script after an unpacked-extension reload on an already-open tab.
manifest_path = Path("apps/extension/public/manifest.json")
manifest = json.loads(manifest_path.read_text())
permissions = list(manifest.get("permissions", []))
if "scripting" not in permissions:
    index = permissions.index("sidePanel") + 1 if "sidePanel" in permissions else len(permissions)
    permissions.insert(index, "scripting")
manifest["permissions"] = permissions
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

build_path = Path("apps/extension/scripts/build-extension.mjs")
build = build_path.read_text()
build = replace_once(
    build,
    '!["nativeMessaging", "sidePanel", "webNavigation"].includes(permission),',
    '!["nativeMessaging", "sidePanel", "scripting", "webNavigation"].includes(\n      permission,\n    ),',
    "mobile scripting exclusion",
)
build_path.write_text(build)

runtime_path = Path("apps/extension/src/background/content-runtime.ts")
runtime_path.write_text(
    r'''export type ContentRuntimeApi = {
  sendMessage<T>(
    tabId: number,
    message: unknown,
    options: { frameId: number },
  ): Promise<T>;
  executeScript(details: {
    target: { tabId: number; frameIds?: number[]; allFrames?: boolean };
    files: string[];
  }): Promise<unknown>;
};

const CONTENT_SCRIPT_FILE = "content/bootstrap.js";

export function isMissingContentReceiverError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return /could not establish connection|receiving end does not exist/i.test(message);
}

function injectedFrameIds(result: unknown): number[] {
  if (!Array.isArray(result)) return [];
  return result
    .map((entry) =>
      entry && typeof entry === "object" && "frameId" in entry
        ? Number((entry as { frameId?: unknown }).frameId)
        : Number.NaN,
    )
    .filter((frameId) => Number.isSafeInteger(frameId) && frameId >= 0);
}

export async function sendWithContentRecovery<T>(
  api: ContentRuntimeApi,
  tabId: number,
  frameId: number,
  message: unknown,
): Promise<T> {
  try {
    return await api.sendMessage<T>(tabId, message, { frameId });
  } catch (error) {
    if (!isMissingContentReceiverError(error)) throw error;
  }

  await api.executeScript({
    target: { tabId, frameIds: [frameId] },
    files: [CONTENT_SCRIPT_FILE],
  });
  return api.sendMessage<T>(tabId, message, { frameId });
}

export async function ensureTabContentRuntime(
  api: ContentRuntimeApi,
  tabId: number,
): Promise<void> {
  let framesToScan = [0];
  try {
    await api.sendMessage(tabId, { type: "CONTENT_PING" }, { frameId: 0 });
  } catch (error) {
    if (!isMissingContentReceiverError(error)) throw error;
    try {
      const injected = await api.executeScript({
        target: { tabId, allFrames: true },
        files: [CONTENT_SCRIPT_FILE],
      });
      framesToScan = [...new Set([0, ...injectedFrameIds(injected)])];
    } catch {
      await api.executeScript({
        target: { tabId, frameIds: [0] },
        files: [CONTENT_SCRIPT_FILE],
      });
      framesToScan = [0];
    }
  }

  for (const frameId of framesToScan) {
    try {
      await sendWithContentRecovery(api, tabId, frameId, {
        type: "CONTENT_SCAN_NOW",
      });
    } catch (error) {
      if (frameId === 0) throw error;
    }
  }
}
'''
)

runtime_test_path = Path("apps/extension/src/background/content-runtime.test.ts")
runtime_test_path.write_text(
    r'''import { describe, expect, it, vi } from "vitest";
import {
  ensureTabContentRuntime,
  isMissingContentReceiverError,
  sendWithContentRecovery,
  type ContentRuntimeApi,
} from "./content-runtime";

function fakeApi(): ContentRuntimeApi & {
  sendMessage: ReturnType<typeof vi.fn>;
  executeScript: ReturnType<typeof vi.fn>;
} {
  return {
    sendMessage: vi.fn(),
    executeScript: vi.fn(),
  } as unknown as ContentRuntimeApi & {
    sendMessage: ReturnType<typeof vi.fn>;
    executeScript: ReturnType<typeof vi.fn>;
  };
}

describe("content runtime recovery", () => {
  it("recognizes Chromium's missing receiver error", () => {
    expect(
      isMissingContentReceiverError(
        new Error("Could not establish connection. Receiving end does not exist."),
      ),
    ).toBe(true);
    expect(isMissingContentReceiverError(new Error("Permission denied"))).toBe(
      false,
    );
  });

  it("does not inject while the receiver is healthy", async () => {
    const runtime = fakeApi();
    runtime.sendMessage.mockResolvedValue({ ok: true });
    await expect(
      sendWithContentRecovery(runtime, 3, 0, { type: "TEST" }),
    ).resolves.toEqual({ ok: true });
    expect(runtime.executeScript).not.toHaveBeenCalled();
  });

  it("reinjects and retries the exact missing frame", async () => {
    const runtime = fakeApi();
    runtime.sendMessage
      .mockRejectedValueOnce(
        new Error("Could not establish connection. Receiving end does not exist."),
      )
      .mockResolvedValueOnce({ result: "recovered" });
    runtime.executeScript.mockResolvedValue([{ frameId: 2 }]);

    await expect(
      sendWithContentRecovery(runtime, 7, 2, { type: "TEST" }),
    ).resolves.toEqual({ result: "recovered" });
    expect(runtime.executeScript).toHaveBeenCalledWith({
      target: { tabId: 7, frameIds: [2] },
      files: ["content/bootstrap.js"],
    });
  });

  it("does not hide unrelated messaging failures", async () => {
    const runtime = fakeApi();
    runtime.sendMessage.mockRejectedValue(new Error("Permission denied"));
    await expect(
      sendWithContentRecovery(runtime, 7, 0, { type: "TEST" }),
    ).rejects.toThrow("Permission denied");
    expect(runtime.executeScript).not.toHaveBeenCalled();
  });

  it("restores accessible frames after extension reload and forces scans", async () => {
    const runtime = fakeApi();
    runtime.sendMessage
      .mockRejectedValueOnce(
        new Error("Could not establish connection. Receiving end does not exist."),
      )
      .mockResolvedValue({ ok: true });
    runtime.executeScript.mockResolvedValue([{ frameId: 0 }, { frameId: 4 }]);

    await ensureTabContentRuntime(runtime, 11);
    expect(runtime.executeScript).toHaveBeenCalledWith({
      target: { tabId: 11, allFrames: true },
      files: ["content/bootstrap.js"],
    });
    expect(runtime.sendMessage).toHaveBeenCalledWith(
      11,
      { type: "CONTENT_SCAN_NOW" },
      { frameId: 0 },
    );
    expect(runtime.sendMessage).toHaveBeenCalledWith(
      11,
      { type: "CONTENT_SCAN_NOW" },
      { frameId: 4 },
    );
  });
});
'''
)

bootstrap_path = Path("apps/extension/src/content/bootstrap.ts")
bootstrap_path.write_text(
    r'''import type {
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
  pending = window.setTimeout(() => {
    pending = undefined;
    debounceStartedAt = 0;
    void enqueueSnapshot(false);
  }, Math.min(SCAN_DEBOUNCE_MS, MAX_SCAN_DEBOUNCE_MS - elapsed));
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
'''
)

# Route all page-bound background commands through the missing-receiver recovery layer.
sw_path = Path("apps/extension/src/background/service-worker.ts")
sw = sw_path.read_text()
sw = replace_once(
    sw,
    'import {\n  AutoPilotController,\n  type AutoPilotResumeInput,\n  type AutoPilotStartInput,\n} from "./autopilot-controller";\n',
    'import {\n  AutoPilotController,\n  type AutoPilotResumeInput,\n  type AutoPilotStartInput,\n} from "./autopilot-controller";\nimport {\n  ensureTabContentRuntime,\n  sendWithContentRecovery,\n  type ContentRuntimeApi,\n} from "./content-runtime";\n',
    "runtime import",
)
sw = replace_once(
    sw,
    'const AUTO_PILOT_RUNTIME_STORAGE_KEY = "autopilot-runtime-v1";\n',
    '''const AUTO_PILOT_RUNTIME_STORAGE_KEY = "autopilot-runtime-v1";\n\nconst contentRuntimeApi: ContentRuntimeApi = {\n  sendMessage: async <T>(\n    tabId: number,\n    message: unknown,\n    options: { frameId: number },\n  ): Promise<T> =>\n    (await chrome.tabs.sendMessage(tabId, message, options)) as T,\n  executeScript: async (details) => {\n    if (!chrome.scripting?.executeScript) {\n      throw new Error("Content runtime recovery is unavailable");\n    }\n    return chrome.scripting.executeScript(details);\n  },\n};\n''',
    "runtime adapter",
)
sw = replace_once(
    sw,
    '''  const response = (await chrome.tabs.sendMessage(\n    tabId,\n    {\n      type: "APPLY_FILL_INSTRUCTIONS",\n      instructions: [instruction],\n    },\n    { frameId: instruction.frameId },\n  )) as { results?: FillResult[] } | undefined;''',
    '''  const response = await sendWithContentRecovery<\n    { results?: FillResult[] } | undefined\n  >(contentRuntimeApi, tabId, instruction.frameId, {\n    type: "APPLY_FILL_INSTRUCTIONS",\n    instructions: [instruction],\n  });''',
    "fill recovery",
)
nav_start = sw.index("async function sendNavigationAction(")
nav_end = sw.index("\nasync function sendFilePickerAssist(", nav_start)
nav_block = r'''async function sendNavigationAction(
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
'''
sw = sw[:nav_start] + nav_block + sw[nav_end:]
file_start = sw.index("async function sendFilePickerAssist(")
file_end = sw.index("\nconst autoPilotController", file_start)
file_block = r'''async function sendFilePickerAssist(
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
'''
sw = sw[:file_start] + file_block + sw[file_end:]
sw = replace_once(
    sw,
    '''  if (tab?.id === undefined || !/^https?:\\/\\//.test(tab.url ?? "")) return null;\n  const activePage = await getMergedPageForTab(tab.id);''',
    '''  if (tab?.id === undefined || !/^https?:\\/\\//.test(tab.url ?? "")) return null;\n  await ensureTabContentRuntime(contentRuntimeApi, tab.id);\n  const activePage = await getMergedPageForTab(tab.id);''',
    "active page recovery",
)
sw = replace_once(
    sw,
    '''    const response = await chrome.tabs.sendMessage(\n      tab.id,\n      { type: "APPLY_FILL_INSTRUCTIONS", instructions },\n      { frameId },\n    );''',
    '''    const response = await sendWithContentRecovery<{ results?: unknown[] }>(\n      contentRuntimeApi,\n      tab.id,\n      frameId,\n      { type: "APPLY_FILL_INSTRUCTIONS", instructions },\n    );''',
    "manual fill-plan recovery",
)
sw = replace_once(
    sw,
    '''  const input: AutoPilotStartInput = {\n    tabId,''',
    '''  await ensureTabContentRuntime(contentRuntimeApi, tabId);\n  const input: AutoPilotStartInput = {\n    tabId,''',
    "autopilot start recovery",
)
sw_path.write_text(sw)

# Visibility checks now include hidden/transparent ancestors, which is critical
# for reCAPTCHA frames that stay mounted while their challenge shell is hidden.
scanner_path = Path("apps/extension/src/content/scanner.ts")
scanner = scanner_path.read_text()
visible_start = scanner.index("function isVisible(element: Element): boolean {")
visible_end = scanner.index("\nfunction hash(", visible_start)
visible_block = r'''function hiddenBySelfOrAncestor(element: HTMLElement): boolean {
  let current: HTMLElement | null = element;
  while (current) {
    const style = window.getComputedStyle(current);
    const opacity = Number.parseFloat(style.opacity || "1");
    if (
      current.hidden ||
      current.getAttribute("aria-hidden") === "true" ||
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.visibility === "collapse" ||
      (Number.isFinite(opacity) && opacity <= 0.01)
    ) {
      return true;
    }
    current = current.parentElement;
  }
  return false;
}

function isVisible(element: Element): boolean {
  if (!(element instanceof HTMLElement)) return false;
  if (hiddenBySelfOrAncestor(element)) return false;
  const style = window.getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  const explicitlyPositioned =
    style.position === "absolute" || style.position === "fixed";
  return !explicitlyPositioned || (rect.right > 0 && rect.bottom > 0);
}
'''
scanner = scanner[:visible_start] + visible_block + scanner[visible_end:]
cap_start = scanner.index("function hasActiveCaptchaFrame(): boolean {")
cap_end = scanner.index("\nfunction hasVisibleCaptchaPrompt", cap_start)
cap_block = r'''function hasActiveCaptchaFrame(): boolean {
  const frames = Array.from(
    document.querySelectorAll(
      "iframe[src*='recaptcha' i], iframe[src*='hcaptcha' i], iframe[src*='challenges.cloudflare.com' i]",
    ),
  );
  return frames.some((frame) => {
    if (!isVisible(frame)) return false;
    const src = frame.getAttribute("src") ?? "";
    const descriptor = normalized(`${src} ${frame.getAttribute("title")}`);

    let captchaSize = "";
    try {
      captchaSize =
        new URL(src, window.location.href).searchParams.get("size") ?? "";
    } catch {
      captchaSize = "";
    }
    if (normalized(captchaSize) === "invisible") return false;
    if (frame.closest(".grecaptcha-badge")) return false;

    const rect = frame.getBoundingClientRect();
    if (/recaptcha/.test(descriptor) && /\/anchor\b/.test(src)) {
      if (/^(normal|compact)$/i.test(captchaSize)) {
        return rect.width >= 180 && rect.height >= 50;
      }
      return rect.width >= 250 && rect.height >= 60;
    }
    if (/\b(bframe|challenge|checkbox)\b/.test(descriptor)) {
      return rect.width >= 180 && rect.height >= 50;
    }
    return rect.width >= 180 && rect.height >= 50;
  });
}
'''
scanner = scanner[:cap_start] + cap_block + scanner[cap_end:]
scanner_path.write_text(scanner)

# Required-marker normalization and pronoun semantics fix the exact labels seen
# on the live Levin form.
contracts_path = Path("packages/contracts/src/index.ts")
contracts = contracts_path.read_text()
contracts = replace_once(
    contracts,
    '  "PREFERRED_NAME",\n  "CONTACT",',
    '  "PREFERRED_NAME",\n  "PRONOUNS",\n  "CONTACT",',
    "pronouns contract",
)
contracts_path.write_text(contracts)

semantic_path = Path("packages/semantic-engine/src/index.ts")
semantic = semantic_path.read_text()
semantic = replace_once(
    semantic,
    '  {\n    id: "full-name",',
    '  {\n    id: "pronouns",\n    pattern: /^(preferred )?pronouns?$/i,\n    semanticType: "PRONOUNS",\n  },\n  {\n    id: "full-name",',
    "pronoun rule",
)
normalize_start = semantic.index("function normalize(text: string): string {")
normalize_end = semantic.index("\nexport function classifyQuestion", normalize_start)
normalize_block = r'''function normalize(text: string): string {
  return text
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\s*\*+\s*$/, "")
    .replace(/\s*\(?required\)?\s*$/i, "")
    .replace(/\s*:\s*$/, "")
    .trim();
}
'''
semantic = semantic[:normalize_start] + normalize_block + semantic[normalize_end:]
semantic_path.write_text(semantic)

resolver_path = Path("packages/application-model/src/resolver.ts")
resolver = resolver_path.read_text()
resolver = replace_once(
    resolver,
    '  PREFERRED_NAME: "preferred_name",\n  CONTACT: "email",',
    '  PREFERRED_NAME: "preferred_name",\n  PRONOUNS: "pronouns",\n  CONTACT: "email",',
    "pronouns resolver",
)
resolver = replace_once(
    resolver,
    '''  const requiresReview =\n    question.requiresReview ||\n    question.sensitive ||\n    fact.protected ||\n    (fact.protected && !fact.confirmedAt);''',
    '''  const requiresReview =\n    question.requiresReview ||\n    question.sensitive ||\n    (fact.protected && !fact.confirmedAt);''',
    "confirmed protected review policy",
)
resolver_path.write_text(resolver)

for profile_file in (
    Path("apps/extension/src/sidepanel/App.tsx"),
    Path("apps/owner-workspace/app/workspace/mobile-workspace.tsx"),
):
    text = profile_file.read_text()
    text = replace_once(
        text,
        '  { section: "Identity", key: "preferred_name", label: "Preferred name", category: "IDENTITY", protected: false },\n  { section: "Identity", key: "legal_name",',
        '  { section: "Identity", key: "preferred_name", label: "Preferred name", category: "IDENTITY", protected: false },\n  { section: "Identity", key: "pronouns", label: "Preferred pronouns", category: "IDENTITY", protected: true },\n  { section: "Identity", key: "legal_name",',
        f"pronouns profile field {profile_file}",
    )
    profile_file.write_text(text)

mobile_path = Path("apps/owner-workspace/app/workspace/mobile-workspace.tsx")
mobile = mobile_path.read_text()
map_start = mobile.index("const semanticFactKey: Record<string, string> = {")
map_end = mobile.index("\n};", map_start) + 3
mobile_map = r'''const semanticFactKey: Record<string, string> = {
  PERSONAL: "legal_name",
  FIRST_NAME: "first_name",
  MIDDLE_NAME: "middle_name",
  LAST_NAME: "last_name",
  PREFERRED_NAME: "preferred_name",
  PRONOUNS: "pronouns",
  EMAIL: "email",
  PHONE: "phone",
  STREET_ADDRESS: "street_address",
  ADDRESS_LINE_2: "address_line_2",
  CITY: "city",
  STATE_PROVINCE: "state",
  POSTAL_CODE: "postal_code",
  COUNTRY: "country",
  LINKEDIN: "linkedin",
  PORTFOLIO: "portfolio",
  WEBSITE: "portfolio",
  WORK_AUTHORIZATION_CURRENT: "work_authorization",
  SPONSORSHIP_CURRENT: "current_sponsorship",
  SPONSORSHIP_FUTURE: "future_sponsorship",
  IMMIGRATION_ASSISTANCE: "immigration_assistance",
  START_DATE: "earliest_start_date",
  NOTICE_PERIOD: "notice_period",
  RELOCATION: "relocation_willingness",
  TRAVEL: "travel_willingness",
  REFERRAL: "referral_source",
};'''
mobile = mobile[:map_start] + mobile_map + mobile[map_end:]
mobile_path.write_text(mobile)

# Regression tests for all four observed live failure classes.
semantic_test_path = Path("packages/semantic-engine/src/index.test.ts")
semantic_tests = semantic_test_path.read_text()
marker = 'describe("classifyQuestion", () => {'
if 'classifies required-marker identity labels from live ATS forms' not in semantic_tests:
    semantic_tests = semantic_tests.replace(
        marker,
        marker
        + r'''
  it("classifies required-marker identity labels from live ATS forms", () => {
    expect(classifyQuestion("First Name *").semanticType).toBe("FIRST_NAME");
    expect(classifyQuestion("Last Name*").semanticType).toBe("LAST_NAME");
    expect(classifyQuestion("Preferred Pronouns *").semanticType).toBe("PRONOUNS");
  });
''',
        1,
    )
semantic_test_path.write_text(semantic_tests)

resolver_test_path = Path("packages/application-model/src/resolver.test.ts")
resolver_tests = resolver_test_path.read_text()
marker = '  it("forces protected facts through review even when confirmed", () => {'
if 'allows explicitly confirmed ordinary protected identity facts' not in resolver_tests:
    extra = r'''  it("allows explicitly confirmed ordinary protected identity facts", () => {
    const result = resolveProfileAnswer(
      question({ semanticType: "FIRST_NAME", rawText: "First Name *" }),
      profile([fact({ protected: true, confirmedAt: now })]),
    );
    expect(result.state).toBe("READY");
    expect(result.value).toBe("Aadil");
    expect(result.protected).toBe(true);
  });

  it("still reviews an ordinary protected identity fact without confirmation", () => {
    const result = resolveProfileAnswer(
      question({ semanticType: "FIRST_NAME", rawText: "First Name *" }),
      profile([fact({ protected: true, confirmedAt: null })]),
    );
    expect(result.state).toBe("REVIEW");
    expect(result.reasons).toContain(
      "Protected source fact has not been explicitly confirmed",
    );
  });

'''
    resolver_tests = resolver_tests.replace(marker, extra + marker, 1)
resolver_test_path.write_text(resolver_tests)

scanner_test_path = Path("apps/extension/src/content/scanner.test.ts")
scanner_tests = scanner_test_path.read_text()
marker = '  it("detects a visible active CAPTCHA challenge", () => {'
if 'ignores anti-bot challenge frames hidden by an ancestor' not in scanner_tests:
    extra = r'''  it("ignores anti-bot challenge frames hidden by an ancestor", () => {
    document.body.innerHTML = `
      <label for="first">First Name *</label>
      <input id="first" required>
      <div style="opacity: 0">
        <iframe title="recaptcha challenge" src="https://www.google.com/recaptcha/api2/bframe"></iframe>
      </div>
    `;
    const frame = document.querySelector("iframe") as HTMLIFrameElement;
    vi.spyOn(frame, "getBoundingClientRect").mockReturnValue({
      ...visibleRectangle,
      bottom: 500,
      height: 400,
      right: 500,
      width: 400,
    });
    expect(scanDocument().securityCheckpoint).toBeNull();
  });

  it("ignores an explicitly invisible CAPTCHA frame with challenge tokens", () => {
    document.body.innerHTML = `
      <label for="email">Email Address *</label>
      <input id="email" type="email" required>
      <iframe title="recaptcha challenge" src="https://www.google.com/recaptcha/api2/bframe?size=invisible"></iframe>
    `;
    const frame = document.querySelector("iframe") as HTMLIFrameElement;
    vi.spyOn(frame, "getBoundingClientRect").mockReturnValue({
      ...visibleRectangle,
      bottom: 500,
      height: 400,
      right: 500,
      width: 400,
    });
    expect(scanDocument().securityCheckpoint).toBeNull();
  });

'''
    scanner_tests = scanner_tests.replace(marker, extra + marker, 1)
scanner_test_path.write_text(scanner_tests)

report = Path("docs/reports/LIVE_ATS_RELIABILITY_REPAIR_2026-08-15.md")
report.write_text(
    """# Live ATS reliability repair — 2026-08-15

## Trigger

A physical Edge smoke test on a Levin application exposed independent failures not covered by the earlier synthetic gate: a hidden/passive anti-bot frame could still be classified as an active CAPTCHA; an extension reload could leave the already-open application tab without a valid content-script receiver; continuously mutating ATS DOM could starve a forced post-fill snapshot until AutoPilot timed out after filling only email; and visible required markers (`First Name *`, `Last Name *`, `Preferred Pronouns *`) prevented deterministic identity classification.

## Repair

- Desktop `scripting` permission is used only to re-inject MUNSHI's own content runtime when Chromium reports that the receiving end does not exist. The active-page read, AutoPilot start, guarded fill, navigation, and file handoff all use the recovery path.
- The content runtime supports health ping and forced scan commands. Forced post-action scans are immediate and serialized; ordinary mutation scans have a maximum debounce horizon so persistent page animation cannot starve state publication.
- CAPTCHA detection now evaluates ancestor visibility and passive/invisible exclusions before treating a challenge frame as active. Genuine visible CAPTCHA remains an owner checkpoint.
- Semantic normalization removes visible required markers before deterministic classification. `PRONOUNS` is now a first-class semantic type with desktop/hosted profile storage.
- A protected ordinary fact can be ready after explicit owner confirmation. Unconfirmed protected data and sensitive/high-risk questions remain review-gated. Sponsorship/authorization safety policy remains unchanged.
- Hosted deterministic profile lookup was aligned with desktop identity, address, availability, and referral keys.

## Security boundary

This change does not solve, bypass, suppress, or evade CAPTCHA or other anti-bot controls. Final submission, CAPTCHA, MFA, OTP, identity verification, authentication, security challenges, and operating-system file selection remain owner actions.
"""
)
