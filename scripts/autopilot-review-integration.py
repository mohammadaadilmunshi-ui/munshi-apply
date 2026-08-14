from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"expected exactly one match in {path}, found {count}: {old[:120]!r}"
        )
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    start_index = text.find(start)
    end_index = text.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise SystemExit(
            f"unable to locate replacement range in {path}: {start!r} -> {end!r}"
        )
    target.write_text(text[:start_index] + replacement + text[end_index:], encoding="utf-8")


# Contracts: file-selection state is a boolean only. No file path/name is serialized.
replace_once(
    "packages/contracts/src/index.ts",
    '  validationMessage: z.string().default(""),\n});',
    '  validationMessage: z.string().default(""),\n  fileSelected: z.boolean().optional(),\n});',
)

# Scanner: retain hidden employer file inputs for owner handoff, while preserving truthful
# visibility metadata and exposing only whether a selection exists.
replace_once(
    "apps/extension/src/content/scanner.ts",
    "function createControl(element: Element): Control | null {\n  if (!isVisible(element)) return null;\n",
    "function createControl(element: Element): Control | null {\n"
    "  const visible = isVisible(element);\n"
    '  const fileInput = element instanceof HTMLInputElement && element.type === "file";\n'
    "  if (!visible && !fileInput) return null;\n",
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    "    visible: true,\n    options: optionsFor(element),",
    "    visible,\n    options: optionsFor(element),",
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    "    validationMessage: validation.validationMessage,\n  };",
    "    validationMessage: validation.validationMessage,\n"
    "    fileSelected:\n"
    '      element instanceof HTMLInputElement && element.type === "file"\n'
    "        ? Boolean(element.files?.length)\n"
    "        : undefined,\n"
    "  };",
)

# AutoPilot launch planning: hidden file inputs still require owner handoff. A newly observed
# file selection stops blocking preflight; hidden non-file controls remain ineligible.
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    "    if (!control || control.disabled || !control.visible) continue;\n"
    '    if (control.kind === "FILE") {\n'
    "      if (!control.fileSelected) manual.set(control.controlId, control);\n"
    "      continue;\n"
    "    }",
    "    if (!control || control.disabled) continue;\n"
    '    if (control.kind === "FILE") {\n'
    "      if (!control.fileSelected) manual.set(control.controlId, control);\n"
    "      continue;\n"
    "    }\n"
    "    if (!control.visible) continue;",
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    "      control.visible &&\n      !control.disabled &&\n      control.required &&",
    "      !control.disabled &&\n"
    "      control.required &&\n"
    '      (control.kind === "FILE" || control.visible) &&',
)

# Fill hardening: a separate verification timeout and exact-match/rollback behavior for native
# controls. This complements the existing async combobox/portaled-option support.
replace_once(
    "apps/extension/src/content/fill.ts",
    "export type FillInteractionOptions = {\n"
    "  optionTimeoutMs?: number;\n"
    "  pollIntervalMs?: number;\n"
    "};\n\n"
    "const DEFAULT_OPTION_TIMEOUT_MS = 1_200;\n"
    "const DEFAULT_POLL_INTERVAL_MS = 25;",
    "export type FillInteractionOptions = {\n"
    "  optionTimeoutMs?: number;\n"
    "  pollIntervalMs?: number;\n"
    "  verificationTimeoutMs?: number;\n"
    "};\n\n"
    "const DEFAULT_OPTION_TIMEOUT_MS = 1_200;\n"
    "const DEFAULT_POLL_INTERVAL_MS = 25;\n"
    "const DEFAULT_VERIFICATION_TIMEOUT_MS = 500;",
)
replace_between(
    "apps/extension/src/content/fill.ts",
    "function fillRadio(element: HTMLInputElement, value: string): boolean {",
    "function fillCheckbox(element: HTMLInputElement, value: string): boolean {",
    '''function radioMatches(candidate: HTMLInputElement, requested: string): boolean {
  const values = radioCandidateValues(candidate);
  if (values.includes(requested)) return true;
  if (["true", "yes", "1", "checked"].includes(requested)) {
    return values.some((value) => ["true", "yes", "1"].includes(value));
  }
  if (["false", "no", "0", "unchecked"].includes(requested)) {
    return values.some((value) => ["false", "no", "0"].includes(value));
  }
  return false;
}

function fillRadio(element: HTMLInputElement, value: string): boolean {
  const requested = normalized(value);
  const candidates = radioCandidates(element).filter((candidate) =>
    radioMatches(candidate, requested),
  );
  if (candidates.length !== 1) return false;
  const match = candidates[0]!;
  match.focus();
  setNativeChecked(match, true);
  dispatchValueEvents(match);
  return match.checked;
}

''',
)
hardened_fill = '''function elementUnavailable(element: Element): boolean {
  if (!(element instanceof HTMLElement)) return true;
  if (element.getAttribute("aria-disabled") === "true") return true;
  if ("disabled" in element && Boolean((element as HTMLInputElement).disabled)) return true;
  return false;
}

async function waitForVerification(
  verify: () => boolean,
  timeoutMilliseconds: number,
  pollIntervalMilliseconds: number,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMilliseconds;
  while (Date.now() <= deadline) {
    if (verify()) return true;
    await delay(pollIntervalMilliseconds);
  }
  return verify();
}

function radioVerified(element: HTMLInputElement, value: string): boolean {
  const requested = normalized(value);
  const checked = radioCandidates(element).filter((candidate) => candidate.checked);
  return checked.length === 1 && radioMatches(checked[0]!, requested);
}

async function fillElement(
  element: Element,
  value: string,
  options: Required<FillInteractionOptions>,
): Promise<boolean> {
  if (elementUnavailable(element)) return false;
  if (
    element instanceof HTMLElement &&
    element.getAttribute("role") === "combobox"
  ) {
    return fillCombobox(element, value, options);
  }
  if (element instanceof HTMLInputElement) {
    if (
      ["file", "password", "hidden", "submit", "button", "reset"].includes(
        element.type,
      )
    ) {
      return false;
    }
    if (element.readOnly && !["radio", "checkbox"].includes(element.type)) {
      return false;
    }
    if (element.type === "radio") {
      const group = radioCandidates(element);
      const original = group.map((candidate) => candidate.checked);
      if (!fillRadio(element, value)) return false;
      const verified = await waitForVerification(
        () => radioVerified(element, value),
        options.verificationTimeoutMs,
        options.pollIntervalMs,
      );
      if (!verified) {
        group.forEach((candidate, index) => {
          setNativeChecked(candidate, original[index] ?? false);
          dispatchValueEvents(candidate);
        });
      }
      return verified;
    }
    if (element.type === "checkbox") {
      const original = element.checked;
      if (!fillCheckbox(element, value)) return false;
      const requested = normalized(value);
      const shouldCheck = ["true", "yes", "1", "checked"].includes(requested);
      const verified = await waitForVerification(
        () => element.checked === shouldCheck,
        options.verificationTimeoutMs,
        options.pollIntervalMs,
      );
      if (!verified) {
        setNativeChecked(element, original);
        dispatchValueEvents(element);
      }
      return verified;
    }
    if (element.type === "date") {
      const original = element.value;
      if (!fillDate(element, value)) return false;
      const requested = canonicalDate(value);
      const verified =
        Boolean(requested) &&
        (await waitForVerification(
          () => element.value === requested && element.validity.valid,
          options.verificationTimeoutMs,
          options.pollIntervalMs,
        ));
      if (!verified) {
        setNativeValue(element, original);
        dispatchValueEvents(element);
      }
      return verified;
    }
    const original = element.value;
    element.focus();
    setNativeValue(element, value);
    dispatchValueEvents(element);
    const verified = await waitForVerification(
      () => element.value === value && element.validity.valid,
      options.verificationTimeoutMs,
      options.pollIntervalMs,
    );
    if (!verified) {
      setNativeValue(element, original);
      dispatchValueEvents(element);
    }
    return verified;
  }
  if (element instanceof HTMLTextAreaElement) {
    if (element.readOnly) return false;
    const original = element.value;
    element.focus();
    setNativeValue(element, value);
    dispatchValueEvents(element);
    const verified = await waitForVerification(
      () => element.value === value && element.validity.valid,
      options.verificationTimeoutMs,
      options.pollIntervalMs,
    );
    if (!verified) {
      setNativeValue(element, original);
      dispatchValueEvents(element);
    }
    return verified;
  }
  if (element instanceof HTMLSelectElement) {
    if (element.multiple) return fillNativeMultiSelect(element, value);
    const requested = normalized(value);
    const matches = Array.from(element.options).filter(
      (candidate) =>
        normalized(candidate.value) === requested ||
        normalized(candidate.text) === requested,
    );
    if (matches.length !== 1) return false;
    const option = matches[0]!;
    const original = element.value;
    element.focus();
    element.value = option.value;
    dispatchValueEvents(element);
    const verified = await waitForVerification(
      () => element.value === option.value && element.validity.valid,
      options.verificationTimeoutMs,
      options.pollIntervalMs,
    );
    if (!verified) {
      element.value = original;
      dispatchValueEvents(element);
    }
    return verified;
  }
  if (element instanceof HTMLElement && element.isContentEditable) {
    const original = element.textContent ?? "";
    element.focus();
    element.textContent = value;
    dispatchValueEvents(element);
    const verified = await waitForVerification(
      () => element.textContent === value,
      options.verificationTimeoutMs,
      options.pollIntervalMs,
    );
    if (!verified) {
      element.textContent = original;
      dispatchValueEvents(element);
    }
    return verified;
  }
  return false;
}

export type FilePickerAssistResult = {
  status: "OWNER_ACTION_REQUESTED" | "REFUSED";
  reason: string;
};

export function assistFilePicker(controlId: string): FilePickerAssistResult {
  const element = controlElementMap().get(controlId);
  if (
    !(element instanceof HTMLInputElement) ||
    element.type !== "file" ||
    element.disabled ||
    element.getAttribute("aria-disabled") === "true"
  ) {
    return {
      status: "REFUSED",
      reason: "The employer file input changed, is disabled, or is unavailable",
    };
  }
  element.focus();
  element.click();
  return {
    status: "OWNER_ACTION_REQUESTED",
    reason:
      "Employer file picker requested. File selection remains an explicit owner action.",
  };
}

'''
replace_between(
    "apps/extension/src/content/fill.ts",
    "async function fillElement(",
    "export async function applyFillInstructions(",
    hardened_fill,
)
replace_once(
    "apps/extension/src/content/fill.ts",
    "    pollIntervalMs:\n"
    "      interactionOptions.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,\n"
    "  };",
    "    pollIntervalMs:\n"
    "      interactionOptions.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,\n"
    "    verificationTimeoutMs:\n"
    "      interactionOptions.verificationTimeoutMs ?? DEFAULT_VERIFICATION_TIMEOUT_MS,\n"
    "  };",
)

# Content runtime: file-picker assistance can only request the employer's picker.
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    'import { applyFillInstructions } from "./fill";',
    'import { applyFillInstructions, assistFilePicker } from "./fill";',
)
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    '    if (message.type === "APPLY_NAVIGATION_ACTION" && message.controlId) {\n'
    "      sendResponse({ result: applyNavigationAction(message.controlId) });\n"
    "      scheduleScan(true);\n"
    "      return false;\n"
    "    }",
    '    if (message.type === "APPLY_FILE_PICKER_ASSIST" && message.controlId) {\n'
    "      sendResponse({ result: assistFilePicker(message.controlId) });\n"
    "      scheduleScan(true);\n"
    "      return false;\n"
    "    }\n"
    '    if (message.type === "APPLY_NAVIGATION_ACTION" && message.controlId) {\n'
    "      sendResponse({ result: applyNavigationAction(message.controlId) });\n"
    "      scheduleScan(true);\n"
    "      return false;\n"
    "    }",
)

# Session model: explicit owner pause and a fresh-observation resume path.
replace_once(
    "packages/application-model/src/autopilot-session.ts",
    '  "WAITING_NAVIGATION",\n  "PAUSED_REVIEW",',
    '  "WAITING_NAVIGATION",\n  "PAUSED_OWNER",\n  "PAUSED_REVIEW",',
)
replace_once(
    "packages/application-model/src/autopilot-session.ts",
    '  | { type: "PAUSE_REVIEW"; reason: string; at: string }',
    '  | { type: "PAUSE_OWNER"; reason: string; at: string }\n'
    '  | { type: "RESUME"; observation: AutoPilotObservation; at: string }\n'
    '  | { type: "PAUSE_REVIEW"; reason: string; at: string }',
)
replace_once(
    "packages/application-model/src/autopilot-session.ts",
    '    case "PAUSE_REVIEW":\n      return {',
    '''    case "PAUSE_OWNER":
      return {
        ...current,
        status: "PAUSED_OWNER",
        securityCheckpoint: null,
        pauseReason: requiredString(action.reason, "reason"),
        updatedAt: action.at,
      };

    case "RESUME":
      if (
        !["PAUSED_OWNER", "PAUSED_REVIEW", "PAUSED_SECURITY"].includes(
          current.status,
        )
      ) {
        return {
          ...current,
          status: "PAUSED_ERROR",
          pauseReason:
            "AutoPilot can resume only from an owner-review/security pause",
          updatedAt: action.at,
        };
      }
      return withObservation(
        { ...current, securityCheckpoint: null, pauseReason: null },
        action.observation,
        action.at,
        "RUNNING",
      );

    case "PAUSE_REVIEW":
      return {''',
)

# Controller: persist owner pause via the existing native checkpoint path, and allow resume only
# from explicit owner/review/security pauses after a current page/preflight refresh.
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "export type AutoPilotStartInput = {\n"
    "  tabId: number;\n"
    "  applicationId: string;\n"
    "  preflight: PreflightGateSummary;\n"
    "  fillInstructions: readonly FillInstruction[];\n"
    "  selectedResumeId: string | null;\n"
    "  selectedResumeSha256: string | null;\n"
    "};",
    "export type AutoPilotStartInput = {\n"
    "  tabId: number;\n"
    "  applicationId: string;\n"
    "  preflight: PreflightGateSummary;\n"
    "  fillInstructions: readonly FillInstruction[];\n"
    "  selectedResumeId: string | null;\n"
    "  selectedResumeSha256: string | null;\n"
    "};\n\n"
    "export type AutoPilotResumeInput = {\n"
    "  preflight: PreflightGateSummary;\n"
    "  fillInstructions: readonly FillInstruction[];\n"
    "};",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '      | { type: "REVIEW"; reason: string }\n      | {',
    '      | { type: "OWNER"; reason: string }\n'
    '      | { type: "REVIEW"; reason: string }\n'
    "      | {",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '      if (action.type === "REVIEW") {\n'
    "        session = reduceAutoPilotSession(session, {",
    '''      if (action.type === "OWNER") {
        session = reduceAutoPilotSession(session, {
          type: "PAUSE_OWNER",
          reason: action.reason,
          at: this.now(),
        });
      } else if (action.type === "REVIEW") {
        session = reduceAutoPilotSession(session, {''',
)
controller_methods = '''  async pause(
    reason = "Paused by owner",
  ): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      const runtime = await this.load();
      if (!runtime) return null;
      if (runtime.session.status !== "RUNNING") {
        throw new Error(
          "AutoPilot can be owner-paused only between verified actions",
        );
      }
      const page = await this.dependencies.getPage(runtime.tabId);
      if (!page) throw new Error("No active application page is available");
      const paused = await this.persistPause(
        runtime,
        observationFor(runtime, page),
        { type: "OWNER", reason },
      );
      return this.statusFromRuntime(paused);
    });
  }

  async resume(
    input: AutoPilotResumeInput,
  ): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      let runtime = await this.load();
      if (!runtime) return null;
      if (
        !["PAUSED_OWNER", "PAUSED_REVIEW", "PAUSED_SECURITY"].includes(
          runtime.session.status,
        )
      ) {
        throw new Error("This AutoPilot state is not safely resumable");
      }
      const page = await this.dependencies.getPage(runtime.tabId);
      if (!page) throw new Error("No active application page is available");
      if (new URL(page.url).origin !== new URL(runtime.lastUrl).origin) {
        throw new Error("Application origin changed while AutoPilot was paused");
      }
      const preflight = parsePreflight(input.preflight);
      const instructions = parseFillInstructions(input.fillInstructions);
      const completed = new Set(runtime.session.completedControlIds);
      const session = reduceAutoPilotSession(
        parseAutoPilotSession({
          ...runtime.session,
          pendingControlIds: instructions
            .filter((instruction) => instruction.approved)
            .map((instruction) => instruction.controlId)
            .filter((controlId) => !completed.has(controlId)),
        }),
        {
          type: "RESUME",
          observation: observationFor(runtime, page),
          at: this.now(),
        },
      );
      runtime = parseAutoPilotRuntimeState({
        ...runtime,
        session,
        preflight,
        fillInstructions: instructions,
        lastUrl: page.url,
        waitingFor: null,
        beforeNavigation: null,
        actionDeadlineAt: null,
        dispatchingFillControlId: null,
        navigationDispatchAttempted: false,
      });
      await this.persist(runtime);
      if (runtime.session.status === "RUNNING") {
        runtime = await this.executeRunningStep(runtime, page);
      }
      return this.statusFromRuntime(runtime);
    });
  }

'''
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '  async stop(\n    reason = "Stopped by owner",',
    controller_methods + '  async stop(\n    reason = "Stopped by owner",',
)

# Service worker lifecycle routes and file-picker owner handoff.
replace_once(
    "apps/extension/src/background/service-worker.ts",
    "  AutoPilotController,\n"
    "  type AutoPilotStartInput,\n"
    '} from "./autopilot-controller";',
    "  AutoPilotController,\n"
    "  type AutoPilotResumeInput,\n"
    "  type AutoPilotStartInput,\n"
    '} from "./autopilot-controller";',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '  | { type: "AUTOPILOT_START"; payload: AutoPilotStartPayload }\n'
    '  | { type: "AUTOPILOT_STOP"; payload?: { reason?: string } }\n'
    '  | { type: "AUTOPILOT_STATUS" };',
    '  | { type: "AUTOPILOT_START"; payload: AutoPilotStartPayload }\n'
    '  | { type: "AUTOPILOT_PAUSE"; payload?: { reason?: string } }\n'
    '  | { type: "AUTOPILOT_RESUME"; payload: AutoPilotResumeInput }\n'
    '  | { type: "AUTOPILOT_STOP"; payload?: { reason?: string } }\n'
    '  | { type: "AUTOPILOT_STATUS" }\n'
    "  | {\n"
    '      type: "AUTOPILOT_ASSIST_FILE";\n'
    "      payload: { frameId: number; controlId: string };\n"
    "    };",
)
file_assist = '''async function sendFilePickerAssist(
  tabId: number,
  frameId: number,
  controlId: string,
): Promise<unknown> {
  const response = (await chrome.tabs.sendMessage(
    tabId,
    { type: "APPLY_FILE_PICKER_ASSIST", controlId },
    { frameId },
  )) as { result?: unknown } | undefined;
  if (!response?.result) {
    throw new Error("File-picker handoff returned no verification result");
  }
  return response.result;
}

'''
replace_once(
    "apps/extension/src/background/service-worker.ts",
    "const autoPilotController = new AutoPilotController({",
    file_assist + "const autoPilotController = new AutoPilotController({",
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '      case "AUTOPILOT_START":\n'
    "        return { ok: true, data: await autoPilotStart(request.payload) };\n"
    '      case "AUTOPILOT_STOP":',
    '''      case "AUTOPILOT_START":
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
      case "AUTOPILOT_STOP":''',
)

# Messaging client: preserve profile coalescing and add typed owner runtime operations.
Path("apps/extension/src/messaging/client.ts").write_text(
    '''import type {
  AutoPilotSession,
  PreflightGateSummary,
} from "@munshi-apply/application-model";
import type {
  ApplicationPage,
  FillInstruction,
  FillPlan,
  FillResult,
  ExtensionRequest,
  ExtensionResponse,
} from "@munshi-apply/contracts";
import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";

export type ExtensionRuntimeHealth = {
  status: string;
  version: string;
  platform: string;
  mobile: boolean;
  capabilities: {
    nativeMessaging: boolean;
    sidePanel: boolean;
  };
};

export type NativeRuntimeHealth = {
  status: string;
  database: string;
  migration_count: number;
  schema_version: string;
  outbox: Record<string, number>;
};

export type AutoPilotControllerStatus = {
  session: AutoPilotSession;
  tabId: number;
  lastUrl: string;
  waitingFor: "FILL" | "NAVIGATION" | null;
  actionDeadlineAt: string | null;
};

export type AutoPilotStartPayload = {
  applicationId: string;
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
};

export type AutoPilotResumePayload = {
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
};

type AutoPilotRuntimeRequest =
  | { type: "AUTOPILOT_START"; payload: AutoPilotStartPayload }
  | { type: "AUTOPILOT_PAUSE"; payload?: { reason?: string } }
  | { type: "AUTOPILOT_RESUME"; payload: AutoPilotResumePayload }
  | { type: "AUTOPILOT_STOP"; payload?: { reason?: string } }
  | { type: "AUTOPILOT_STATUS" }
  | {
      type: "AUTOPILOT_ASSIST_FILE";
      payload: { frameId: number; controlId: string };
    };

type ProfileSaveWaiter = {
  resolve: () => void;
  reject: (error: unknown) => void;
};

let queuedProfile: ProfileSnapshot | null = null;
let profileSaveRunning = false;
let profileSaveWaiters: ProfileSaveWaiter[] = [];

async function send(
  request: ExtensionRequest | AutoPilotRuntimeRequest,
): Promise<unknown> {
  const response = (await chrome.runtime.sendMessage(request)) as ExtensionResponse;
  if (!response.ok) throw new Error(response.error);
  return response.data;
}

async function drainProfileSaveQueue(): Promise<void> {
  let failure: unknown = null;
  try {
    while (queuedProfile) {
      const profile = queuedProfile;
      queuedProfile = null;
      await send({ type: "SAVE_PROFILE", payload: profile });
    }
  } catch (error) {
    failure = error;
    queuedProfile = null;
  } finally {
    profileSaveRunning = false;
    const waiters = profileSaveWaiters;
    profileSaveWaiters = [];
    for (const waiter of waiters) {
      if (failure) waiter.reject(failure);
      else waiter.resolve();
    }
    if (queuedProfile && !profileSaveRunning) {
      profileSaveRunning = true;
      void drainProfileSaveQueue();
    }
  }
}

export async function getActivePage(): Promise<ApplicationPage | null> {
  return (await send({ type: "GET_ACTIVE_PAGE" })) as ApplicationPage | null;
}

export async function getProfile(): Promise<ProfileSnapshot | null> {
  const candidate = await send({ type: "GET_PROFILE" });
  return candidate === null ? null : parseProfileSnapshot(candidate);
}

export function saveProfile(profile: ProfileSnapshot): Promise<void> {
  queuedProfile = parseProfileSnapshot(profile);
  return new Promise((resolve, reject) => {
    profileSaveWaiters.push({ resolve, reject });
    if (profileSaveRunning) return;
    profileSaveRunning = true;
    void drainProfileSaveQueue();
  });
}

export async function getHealth(): Promise<ExtensionRuntimeHealth> {
  return (await send({ type: "PING" })) as ExtensionRuntimeHealth;
}

export async function getNativeHealth(): Promise<NativeRuntimeHealth> {
  return (await send({ type: "NATIVE_HEALTH" })) as NativeRuntimeHealth;
}

export async function applyFillPlan(plan: FillPlan): Promise<FillResult[]> {
  const result = (await send({ type: "APPLY_FILL_PLAN", payload: plan })) as {
    results?: FillResult[];
  };
  return result.results ?? [];
}

export async function getAutoPilotStatus(): Promise<AutoPilotControllerStatus | null> {
  return (await send({ type: "AUTOPILOT_STATUS" })) as AutoPilotControllerStatus | null;
}

export async function startAutoPilot(
  payload: AutoPilotStartPayload,
): Promise<AutoPilotControllerStatus> {
  return (await send({ type: "AUTOPILOT_START", payload })) as AutoPilotControllerStatus;
}

export async function pauseAutoPilot(
  reason = "Paused by owner",
): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_PAUSE",
    payload: { reason },
  })) as AutoPilotControllerStatus | null;
}

export async function resumeAutoPilot(
  payload: AutoPilotResumePayload,
): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_RESUME",
    payload,
  })) as AutoPilotControllerStatus | null;
}

export async function stopAutoPilot(
  reason = "Stopped by owner",
): Promise<AutoPilotControllerStatus | null> {
  return (await send({
    type: "AUTOPILOT_STOP",
    payload: { reason },
  })) as AutoPilotControllerStatus | null;
}

export async function requestFilePickerAssist(
  frameId: number,
  controlId: string,
): Promise<{ status: string; reason: string }> {
  return (await send({
    type: "AUTOPILOT_ASSIST_FILE",
    payload: { frameId, controlId },
  })) as { status: string; reason: string };
}
''',
    encoding="utf-8",
)

# Native AI review lifecycle: retrieve exact approved content only for the same question binding.
store_path = Path("apps/native-host/src/munshi_apply_native/ai_draft_store.py")
store_text = store_path.read_text(encoding="utf-8")
marker = "    def _load_for_update(self, connection: object, draft_id: str) -> object:\n"
approved_method = '''    def approved_for(self, binding: dict[str, object]) -> dict[str, object] | None:
        application_id = _required(binding.get("applicationId"), "applicationId")
        page_id = _required(binding.get("pageId"), "pageId")
        question_id = _required(binding.get("questionId"), "questionId")
        control_id = _required(binding.get("controlId"), "controlId")
        question_fingerprint = _fingerprint(binding)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM ai_drafts
                WHERE application_id = ? AND page_id = ? AND question_id = ?
                  AND control_id = ? AND question_fingerprint = ?
                  AND status IN ('APPROVED', 'USED')
                ORDER BY CASE status WHEN 'APPROVED' THEN 0 ELSE 1 END,
                         generated_at DESC
                LIMIT 1
                """,
                (
                    application_id,
                    page_id,
                    question_id,
                    control_id,
                    question_fingerprint,
                ),
            ).fetchone()
        return None if row is None else self._wire(row)

'''
if store_text.count(marker) != 1:
    raise SystemExit("AI draft store insertion marker is not unique")
store_path.write_text(store_text.replace(marker, approved_method + marker, 1), encoding="utf-8")

# Native messaging operations are local-authoritative and never return credentials.
replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    "from datetime import datetime",
    "from datetime import UTC, datetime",
)
replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    "from .ai_governance import AIGovernanceService",
    "from .ai_draft_store import AIDraftStore\nfrom .ai_governance import AIGovernanceService",
)
replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    '        "GENERATE_AI_DRAFT",\n    }:',
    '        "GENERATE_AI_DRAFT",\n'
    '        "LIST_AI_DRAFTS",\n'
    '        "GET_APPROVED_AI_DRAFT",\n'
    '        "UPDATE_AI_DRAFT",\n'
    '        "APPROVE_AI_DRAFT",\n'
    '        "REJECT_AI_DRAFT",\n'
    '        "MARK_AI_DRAFT_USED",\n'
    "    }:",
)
replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    '        if message_type == "LIST_OPENAI_MODELS":\n'
    '            return {"ok": True, "data": {"models": ai_store.list_models()}}\n'
    "        governance = AIGovernanceService(database, ai_store)",
    '''        if message_type == "LIST_OPENAI_MODELS":
            return {"ok": True, "data": {"models": ai_store.list_models()}}
        if message_type in {
            "LIST_AI_DRAFTS",
            "GET_APPROVED_AI_DRAFT",
            "UPDATE_AI_DRAFT",
            "APPROVE_AI_DRAFT",
            "REJECT_AI_DRAFT",
            "MARK_AI_DRAFT_USED",
        }:
            payload = message.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("AI draft lifecycle payload must be an object")
            drafts = AIDraftStore(database)
            at = datetime.now(UTC).isoformat()
            if message_type == "LIST_AI_DRAFTS":
                application_id = payload.get("applicationId")
                page_id = payload.get("pageId")
                if not isinstance(application_id, str):
                    raise ValueError("AI draft list requires applicationId")
                if page_id is not None and not isinstance(page_id, str):
                    raise ValueError("AI draft pageId must be a string")
                return {
                    "ok": True,
                    "data": drafts.list_for_application(application_id, page_id),
                }
            if message_type == "GET_APPROVED_AI_DRAFT":
                return {"ok": True, "data": drafts.approved_for(payload)}
            draft_id = payload.get("draftId")
            if not isinstance(draft_id, str):
                raise ValueError("AI draft lifecycle request requires draftId")
            if message_type == "UPDATE_AI_DRAFT":
                return {
                    "ok": True,
                    "data": drafts.update_text(
                        draft_id,
                        payload.get("text"),
                        payload.get("expectedSha256"),
                        at,
                    ),
                }
            if message_type == "APPROVE_AI_DRAFT":
                return {
                    "ok": True,
                    "data": drafts.approve(
                        draft_id,
                        payload.get("expectedSha256"),
                        at,
                    ),
                }
            if message_type == "REJECT_AI_DRAFT":
                return {"ok": True, "data": drafts.reject(draft_id, at)}
            return {"ok": True, "data": drafts.mark_used(draft_id, at)}
        governance = AIGovernanceService(database, ai_store)''',
)

# AI governance binds generation to exact page/question/control and persists only validated
# provider output. Provider usage remains recorded even if later draft persistence fails.
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    "from .ai_budget_store import AIBudgetStore",
    "from .ai_budget_store import AIBudgetStore\nfrom .ai_draft_store import AIDraftStore",
)
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    "from .architecture_store import ArchitectureStore",
    "from .application_store import ApplicationStore\nfrom .architecture_store import ArchitectureStore",
)
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    "        self.architecture = ArchitectureStore(database)\n"
    "        self.budget = AIBudgetStore(database)",
    "        self.architecture = ArchitectureStore(database)\n"
    "        self.applications = ApplicationStore(database)\n"
    "        self.budget = AIBudgetStore(database)\n"
    "        self.drafts = AIDraftStore(database)",
)
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    '        application_id = payload.get("applicationId")\n'
    '        question = payload.get("question")\n'
    '        semantic_type = payload.get("semanticType")\n'
    '        correlation_id = payload.get("correlationId")',
    '        application_id = payload.get("applicationId")\n'
    '        page_id = payload.get("pageId")\n'
    '        question_id = payload.get("questionId")\n'
    '        control_id = payload.get("controlId")\n'
    '        question = payload.get("question")\n'
    '        semantic_type = payload.get("semanticType")\n'
    '        correlation_id = payload.get("correlationId")',
)
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    '        if not isinstance(question, str) or not question.strip():\n'
    '            raise ValueError("AI draft request requires question")',
    '        if not isinstance(page_id, str) or not page_id.strip():\n'
    '            raise ValueError("AI draft request requires pageId")\n'
    '        if not isinstance(question_id, str) or not question_id.strip():\n'
    '            raise ValueError("AI draft request requires questionId")\n'
    '        if not isinstance(control_id, str) or not control_id.strip():\n'
    '            raise ValueError("AI draft request requires controlId")\n'
    '        if not isinstance(question, str) or not question.strip():\n'
    '            raise ValueError("AI draft request requires question")',
)
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    '            "applicationId": application_id.strip(),\n'
    '            "question": question.strip(),',
    '            "applicationId": application_id.strip(),\n'
    '            "pageId": page_id.strip(),\n'
    '            "questionId": question_id.strip(),\n'
    '            "controlId": control_id.strip(),\n'
    '            "question": question.strip(),',
)
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    '        correlation_id = str(request["correlationId"])\n'
    '        usage_id = f"ai-use-{reservation_id.removeprefix(\'ai-res-\')}"',
    '        correlation_id = str(request["correlationId"])\n'
    '        self.applications.ensure(str(request["applicationId"]), now.isoformat())\n'
    '        usage_id = f"ai-use-{reservation_id.removeprefix(\'ai-res-\')}"',
)
old_return = '''        return {
            "status": "DRAFT_REVIEW_REQUIRED",
            "provider": "openai",
            "model": result.model,
            "responseId": result.response_id,
            "text": result.text,
            "claims": [
                {
                    "claimId": claim.claim_id,
                    "text": claim.text,
                    "evidenceIds": list(claim.evidence_ids),
                }
                for claim in result.claims
            ],
            "evidenceIds": sorted(evidence_ids),
            "usage": {
                "inputTokens": result.usage.input_tokens,
                "outputTokens": result.usage.output_tokens,
                "totalTokens": result.usage.total_tokens,
                "costUsd": actual_cost,
                "estimated": False,
            },
            "budgetState": prepared["budget"]["state"],
            "reviewRequired": True,
            "approved": False,
        }'''
new_return = '''        claims = [
            {
                "claimId": claim.claim_id,
                "text": claim.text,
                "evidenceIds": list(claim.evidence_ids),
            }
            for claim in result.claims
        ]
        usage = {
            "inputTokens": result.usage.input_tokens,
            "outputTokens": result.usage.output_tokens,
            "totalTokens": result.usage.total_tokens,
            "costUsd": actual_cost,
            "estimated": False,
        }
        draft = self.drafts.create(
            {
                "draftId": f"ai-draft-{uuid.uuid4()}",
                "applicationId": request["applicationId"],
                "pageId": request["pageId"],
                "questionId": request["questionId"],
                "controlId": request["controlId"],
                "question": request["question"],
                "semanticType": request["semanticType"],
                "provider": "openai",
                "model": result.model,
                "responseId": result.response_id,
                "text": result.text,
                "evidenceIds": sorted(evidence_ids),
                "claims": claims,
                "usage": usage,
                "generatedAt": self._now().isoformat(),
            }
        )
        return {
            "status": "DRAFT_REVIEW_REQUIRED",
            "draftId": draft["draftId"],
            "draft": draft,
            "provider": "openai",
            "model": result.model,
            "responseId": result.response_id,
            "text": result.text,
            "claims": claims,
            "evidenceIds": sorted(evidence_ids),
            "usage": usage,
            "budgetState": prepared["budget"]["state"],
            "reviewRequired": True,
            "approved": False,
        }'''
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    old_return,
    new_return,
)

# Extension native protocol: exact draft types, parsing and lifecycle operations.
native_path = Path("apps/extension/src/messaging/native.ts")
native_text = native_path.read_text(encoding="utf-8")
old_request = '''export type AIDraftRequest = {
  applicationId: string;
  question: string;'''
new_request = '''export type AIDraftRequest = {
  applicationId: string;
  pageId: string;
  questionId: string;
  controlId: string;
  question: string;'''
if native_text.count(old_request) != 1:
    raise SystemExit("native.ts AI draft request marker mismatch")
native_text = native_text.replace(old_request, new_request, 1)
draft_types = '''export type AIDraftStatus =
  | "DRAFT"
  | "APPROVED"
  | "REJECTED"
  | "SUPERSEDED"
  | "USED";

export type AIDraftRecord = {
  draftId: string;
  applicationId: string;
  pageId: string;
  questionId: string;
  controlId: string;
  questionFingerprint: string;
  semanticType: string;
  provider: "openai";
  model: string;
  responseId: string;
  originalText: string;
  currentText: string;
  contentSha256: string;
  status: AIDraftStatus;
  evidenceIds: string[];
  claims: { claimId: string; text: string; evidenceIds: string[] }[];
  usage: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    costUsd: number;
    estimated?: boolean;
  };
  generatedAt: string;
  updatedAt: string;
  approvedAt: string | null;
  usedAt: string | null;
};

'''
marker = "export type AIDraftResult = {\n"
if native_text.count(marker) != 1:
    raise SystemExit("native.ts AIDraftResult marker mismatch")
native_text = native_text.replace(marker, draft_types + marker, 1)
native_text = native_text.replace(
    'export type AIDraftResult = {\n  status: "DRAFT_REVIEW_REQUIRED";',
    'export type AIDraftResult = {\n'
    '  status: "DRAFT_REVIEW_REQUIRED";\n'
    "  draftId: string;\n"
    "  draft: AIDraftRecord;",
    1,
)
parser_marker = "function parseCheckpointSaveResult(value: unknown): NativeCheckpointSaveResult {"
draft_parser = '''function parseAIDraftRecord(value: unknown): AIDraftRecord {
  const candidate = objectValue(value, "AI draft");
  const statuses = new Set([
    "DRAFT",
    "APPROVED",
    "REJECTED",
    "SUPERSEDED",
    "USED",
  ]);
  if (typeof candidate.status !== "string" || !statuses.has(candidate.status)) {
    throw new Error("AI draft status is invalid");
  }
  if (candidate.provider !== "openai") {
    throw new Error("AI draft provider is invalid");
  }
  const contentSha256 = stringValue(
    candidate.contentSha256,
    "AI draft contentSha256",
  );
  if (!/^[a-f0-9]{64}$/.test(contentSha256)) {
    throw new Error("AI draft content digest is invalid");
  }
  if (
    !Array.isArray(candidate.evidenceIds) ||
    !candidate.evidenceIds.every(
      (item) => typeof item === "string" && item.trim(),
    )
  ) {
    throw new Error("AI draft evidenceIds are invalid");
  }
  if (!Array.isArray(candidate.claims)) {
    throw new Error("AI draft claims are invalid");
  }
  const claims = candidate.claims.map((item) => {
    const claim = objectValue(item, "AI draft claim");
    if (
      !Array.isArray(claim.evidenceIds) ||
      !claim.evidenceIds.every(
        (entry) => typeof entry === "string" && entry.trim(),
      )
    ) {
      throw new Error("AI draft claim evidence is invalid");
    }
    return {
      claimId: stringValue(claim.claimId, "AI draft claimId"),
      text: stringValue(claim.text, "AI draft claim text"),
      evidenceIds: [...claim.evidenceIds] as string[],
    };
  });
  const usage = objectValue(candidate.usage, "AI draft usage");
  const timestamp = (input: unknown, label: string): string => {
    const result = stringValue(input, label);
    if (Number.isNaN(Date.parse(result))) throw new Error(`${label} is invalid`);
    return result;
  };
  const nullableTimestamp = (
    input: unknown,
    label: string,
  ): string | null =>
    input === null ? null : timestamp(input, label);
  return {
    draftId: stringValue(candidate.draftId, "AI draftId"),
    applicationId: stringValue(candidate.applicationId, "AI applicationId"),
    pageId: stringValue(candidate.pageId, "AI pageId"),
    questionId: stringValue(candidate.questionId, "AI questionId"),
    controlId: stringValue(candidate.controlId, "AI controlId"),
    questionFingerprint: stringValue(
      candidate.questionFingerprint,
      "AI question fingerprint",
    ),
    semanticType: stringValue(candidate.semanticType, "AI semantic type"),
    provider: "openai",
    model: stringValue(candidate.model, "AI model"),
    responseId: stringValue(candidate.responseId, "AI responseId"),
    originalText: stringValue(candidate.originalText, "AI original text"),
    currentText: stringValue(candidate.currentText, "AI current text"),
    contentSha256,
    status: candidate.status as AIDraftStatus,
    evidenceIds: [...candidate.evidenceIds] as string[],
    claims,
    usage: {
      inputTokens: integerValue(usage.inputTokens, "AI draft inputTokens"),
      outputTokens: integerValue(usage.outputTokens, "AI draft outputTokens"),
      totalTokens: integerValue(usage.totalTokens, "AI draft totalTokens"),
      costUsd: finiteNumber(usage.costUsd, "AI draft costUsd"),
      estimated: usage.estimated === true,
    },
    generatedAt: timestamp(candidate.generatedAt, "AI generatedAt"),
    updatedAt: timestamp(candidate.updatedAt, "AI updatedAt"),
    approvedAt: nullableTimestamp(candidate.approvedAt, "AI approvedAt"),
    usedAt: nullableTimestamp(candidate.usedAt, "AI usedAt"),
  };
}

'''
if native_text.count(parser_marker) != 1:
    raise SystemExit("native.ts draft parser marker mismatch")
native_text = native_text.replace(parser_marker, draft_parser + parser_marker, 1)
native_text += '''

export async function listAIDrafts(
  applicationId: string,
  pageId?: string,
): Promise<AIDraftRecord[]> {
  const result = await sendNative<unknown>({
    type: "LIST_AI_DRAFTS",
    payload: { applicationId, pageId },
  });
  if (!Array.isArray(result)) throw new Error("AI draft list is invalid");
  return result.map(parseAIDraftRecord);
}

export async function getApprovedAIDraft(
  request: AIDraftRequest,
): Promise<AIDraftRecord | null> {
  const result = await sendNative<unknown>({
    type: "GET_APPROVED_AI_DRAFT",
    payload: request,
  });
  return result === null ? null : parseAIDraftRecord(result);
}

export async function updateAIDraft(
  draftId: string,
  text: string,
  expectedSha256: string,
): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "UPDATE_AI_DRAFT",
      payload: { draftId, text, expectedSha256 },
    }),
  );
}

export async function approveAIDraft(
  draftId: string,
  expectedSha256: string,
): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "APPROVE_AI_DRAFT",
      payload: { draftId, expectedSha256 },
    }),
  );
}

export async function rejectAIDraft(draftId: string): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "REJECT_AI_DRAFT",
      payload: { draftId },
    }),
  );
}

export async function markAIDraftUsed(
  draftId: string,
): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "MARK_AI_DRAFT_USED",
      payload: { draftId },
    }),
  );
}
'''
native_path.write_text(native_text, encoding="utf-8")

# AI review UI never silently re-enables an approved answer after a panel reload. Owner must
# deliberately choose "Use approved answer" for current-session fill eligibility.
review_path = Path("apps/extension/src/sidepanel/AIDraftReview.tsx")
review_text = review_path.read_text(encoding="utf-8")
review_text = review_text.replace(
    "    if (approved) onApproved(approved.currentText, approved.draftId);\n",
    "",
    1,
)
old_approve_button = '''            <button className="primary" type="button" disabled={busy || !text.trim() || ["REJECTED", "SUPERSEDED", "USED"].includes(draft.status)} onClick={() => void approve()}>
              Approve exact answer
            </button>'''
new_approve_button = '''            <button
              className="primary"
              type="button"
              disabled={
                busy ||
                !text.trim() ||
                ["REJECTED", "SUPERSEDED", "USED"].includes(draft.status) ||
                (draft.status === "APPROVED" && text === draft.currentText)
              }
              onClick={() => void approve()}
            >
              Approve exact answer
            </button>
            {(draft.status === "APPROVED" || draft.status === "USED") && (
              <button
                className="primary"
                type="button"
                disabled={busy}
                onClick={() => onApproved(draft.currentText, draft.draftId)}
              >
                Use approved answer
              </button>
            )}'''
if review_text.count(old_approve_button) != 1:
    raise SystemExit("AI review approval button marker mismatch")
review_path.write_text(
    review_text.replace(old_approve_button, new_approve_button, 1),
    encoding="utf-8",
)

# AutoPilot pause occurs only between verified actions, never while a fill/navigation is in-flight.
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    "  const pausable =\n"
    '    status?.session.status === "RUNNING" ||\n'
    '    status?.session.status === "WAITING_RESCAN" ||\n'
    '    status?.session.status === "WAITING_NAVIGATION";',
    '  const pausable = status?.session.status === "RUNNING";',
)

# Main sidepanel integration: first-class AutoPilot view and AI review bridge.
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "  type ExtensionRuntimeHealth,\n  type NativeRuntimeHealth,",
    "  type AutoPilotControllerStatus,\n"
    "  type ExtensionRuntimeHealth,\n"
    "  type NativeRuntimeHealth,",
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "  listOpenAIModels,\n  saveAISettings,",
    "  listOpenAIModels,\n  markAIDraftUsed,\n  saveAISettings,",
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    'import { AIControlCenter } from "./AIControlCenter";\n\n'
    'type View = "application" | "profile" | "ai" | "diagnostics";',
    'import { AIControlCenter } from "./AIControlCenter";\n'
    'import { AIDraftReview } from "./AIDraftReview";\n'
    'import { AutoPilotControlCenter } from "./AutoPilotControlCenter";\n\n'
    'type View = "application" | "profile" | "autopilot" | "ai" | "diagnostics";',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "type AnswerDraft = {\n"
    "  value: string;\n"
    "  approved: boolean;\n"
    "  sensitive: boolean;\n"
    "};",
    "type AnswerDraft = {\n"
    "  value: string;\n"
    "  approved: boolean;\n"
    "  sensitive: boolean;\n"
    "  sourceDraftId?: string | null;\n"
    "};",
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '  const [aiMessage, setAiMessage] = useState("");',
    '  const [aiMessage, setAiMessage] = useState("");\n'
    "  const [autoPilotStatus, setAutoPilotStatus] =\n"
    "    useState<AutoPilotControllerStatus | null>(null);",
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "  const reviewCount = useMemo(",
    "  const selectedResume = useMemo(\n"
    "    () =>\n"
    "      cloudSnapshot?.resumes.find(\n"
    "        (resume) => resume.resumeId === selectedResumeId,\n"
    "      ) ?? null,\n"
    "    [cloudSnapshot, selectedResumeId],\n"
    "  );\n"
    "  const activeApplicationId =\n"
    '    autoPilotStatus?.session.applicationId ?? page?.pageId ?? "";\n\n'
    "  const reviewCount = useMemo(",
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "      const results = await applyFillPlan({\n"
    "        pageId: page.pageId,\n"
    "        instructions,\n"
    "      });\n"
    "      const filled = results.filter(",
    "      const results = await applyFillPlan({\n"
    "        pageId: page.pageId,\n"
    "        instructions,\n"
    "      });\n"
    "      const usedDraftIds = results\n"
    '        .filter((result) => result.status === "FILLED")\n'
    "        .flatMap((result) => {\n"
    "          const question = page.questions.find(\n"
    "            (candidate) => candidate.controlId === result.controlId,\n"
    "          );\n"
    "          const draftId = question\n"
    "            ? answers[question.questionId]?.sourceDraftId\n"
    "            : null;\n"
    "          return draftId ? [draftId] : [];\n"
    "        });\n"
    "      await Promise.allSettled(\n"
    "        usedDraftIds.map((draftId) => markAIDraftUsed(draftId)),\n"
    "      );\n"
    "      const filled = results.filter(",
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '        {(["application", "profile", "ai", "diagnostics"] as const).map(',
    '        {(["application", "profile", "autopilot", "ai", "diagnostics"] as const).map(',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "                              value: event.target.value,\n"
    "                              approved: false,",
    "                              value: event.target.value,\n"
    "                              approved: false,\n"
    "                              sourceDraftId: null,",
)
approval_marker = '''                      <label className="answer-approval">
                        <input
                          type="checkbox"
                          checked={answer.approved}
                          disabled={!answer.value.trim()}
                          onChange={(event) =>
                            setAnswers((current) => ({
                              ...current,
                              [question.questionId]: {
                                ...answer,
                                approved: event.target.checked,
                              },
                            }))
                          }
                        />
                        Approved for this application
                      </label>'''
approval_with_ai = approval_marker + '''
                      <AIDraftReview
                        applicationId={activeApplicationId || page.pageId}
                        pageId={page.pageId}
                        question={question}
                        nativeAvailable={native.status === "healthy"}
                        onApproved={(value, draftId) =>
                          setAnswers((current) => ({
                            ...current,
                            [question.questionId]: {
                              value,
                              approved: true,
                              sensitive: question.sensitive,
                              sourceDraftId: draftId,
                            },
                          }))
                        }
                      />'''
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    approval_marker,
    approval_with_ai,
)
autopilot_view = '''
      {view === "autopilot" && (
        <AutoPilotControlCenter
          page={page}
          answers={answers}
          applicationId={activeApplicationId || page?.pageId || ""}
          selectedResumeId={selectedResumeId || null}
          selectedResumeSha256={selectedResume?.sha256 ?? null}
          nativeAvailable={native.status === "healthy"}
          onStatusChange={setAutoPilotStatus}
        />
      )}

'''
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '      {view === "profile" && (',
    autopilot_view + '      {view === "profile" && (',
)

# Migration expectations: 007 is now canonical.
replace_once(
    "apps/native-host/tests/test_database.py",
    '        "006_ai_budget_reservations.sql",\n    ]',
    '        "006_ai_budget_reservations.sql",\n'
    '        "007_ai_draft_reviews.sql",\n'
    "    ]",
)
replace_once(
    "apps/native-host/tests/test_database.py",
    '    assert health["migration_count"] == 6\n'
    '    assert health["schema_version"] == "006_ai_budget_reservations.sql"',
    '    assert health["migration_count"] == 7\n'
    '    assert health["schema_version"] == "007_ai_draft_reviews.sql"',
)
replace_once(
    "apps/native-host/tests/test_database.py",
    '            "ai_budget_reservations",\n            "interaction_recipes",',
    '            "ai_budget_reservations",\n'
    '            "ai_drafts",\n'
    '            "interaction_recipes",',
)
replace_once(
    "apps/native-host/tests/test_operations.py",
    '        "006_ai_budget_reservations.sql",\n    ]',
    '        "006_ai_budget_reservations.sql",\n'
    '        "007_ai_draft_reviews.sql",\n'
    "    ]",
)
replace_once(
    "apps/native-host/tests/test_api.py",
    '        assert health.json()["schema_version"] == "006_ai_budget_reservations.sql"',
    '        assert health.json()["schema_version"] == "007_ai_draft_reviews.sql"',
)

# Governance tests bind drafts to exact question identity and verify persistence.
replace_once(
    "apps/native-host/tests/test_ai_governance.py",
    '        "applicationId": "app-1",\n'
    '        "question": "Why are you interested in this role?",',
    '        "applicationId": "app-1",\n'
    '        "pageId": "page-1",\n'
    '        "questionId": "question-1",\n'
    '        "controlId": "control-1",\n'
    '        "question": "Why are you interested in this role?",',
)
replace_once(
    "apps/native-host/tests/test_ai_governance.py",
    '    assert result["evidenceIds"] == ["ev-1"]\n'
    "    with database.connect() as connection:",
    '    assert result["evidenceIds"] == ["ev-1"]\n'
    '    assert result["draft"]["status"] == "DRAFT"\n'
    '    assert result["draft"]["questionId"] == "question-1"\n'
    "    with database.connect() as connection:",
)
replace_once(
    "apps/native-host/tests/test_native_ai_governance_messages.py",
    '                "applicationId": "app-1",\n'
    '                "question": "Why this role?",',
    '                "applicationId": "app-1",\n'
    '                "pageId": "page-1",\n'
    '                "questionId": "q-1",\n'
    '                "controlId": "control-1",\n'
    '                "question": "Why this role?",',
)

# Add a model-level owner pause/resume proof.
session_test = Path("packages/application-model/src/autopilot-session.test.ts")
session_text = session_test.read_text(encoding="utf-8")
session_insert = '''

  it("supports an explicit owner pause and fresh-observation resume", () => {
    const started = reduceAutoPilotSession(freshSession(), {
      type: "START",
      observation,
      at: "2026-08-14T21:00:01.000Z",
    });
    const paused = reduceAutoPilotSession(started, {
      type: "PAUSE_OWNER",
      reason: "Owner requested pause",
      at: "2026-08-14T21:00:02.000Z",
    });
    expect(paused.status).toBe("PAUSED_OWNER");
    const resumed = reduceAutoPilotSession(paused, {
      type: "RESUME",
      observation: { ...observation, pageFingerprint: "fingerprint-2" },
      at: "2026-08-14T21:00:03.000Z",
    });
    expect(resumed.status).toBe("RUNNING");
    expect(resumed.pauseReason).toBeNull();
  });
'''
closing = "\n});\n"
if not session_text.endswith(closing):
    raise SystemExit("autopilot-session.test.ts closing marker mismatch")
session_test.write_text(
    session_text[: -len(closing)] + session_insert + closing,
    encoding="utf-8",
)

# Add regression tests for native ambiguity, async controlled fields and file privacy metadata.
fill_test = Path("apps/extension/src/content/fill.test.ts")
fill_text = fill_test.read_text(encoding="utf-8")
fill_insert = '''

  it("fails closed when a native select has duplicate exact labels", async () => {
    document.body.innerHTML = `
      <label for="state">State</label>
      <select id="state"><option value="NJ">New Jersey</option><option value="NEW_JERSEY">New Jersey</option></select>
    `;
    const question = scanDocument().questions[0]!;
    const result = await applyFillInstructions([{
      controlId: question.controlId,
      frameId: 0,
      value: "New Jersey",
      sensitive: false,
      approved: true,
    }]);
    expect(result[0]?.status).toBe("FAILED");
  });

  it("fails closed when a radio answer maps to more than one exact option", async () => {
    document.body.innerHTML = `
      <fieldset><legend>Preference</legend>
        <label><input type="radio" name="pref" value="Yes"> Yes</label>
        <label><input type="radio" name="pref" value="Yes"> Yes</label>
      </fieldset>
    `;
    const question = scanDocument().questions[0]!;
    const result = await applyFillInstructions([{
      controlId: question.controlId,
      frameId: 0,
      value: "Yes",
      sensitive: false,
      approved: true,
    }]);
    expect(result[0]?.status).toBe("FAILED");
    expect(document.querySelectorAll("input:checked")).toHaveLength(0);
  });

  it("waits for controlled native input verification instead of trusting dispatch", async () => {
    document.body.innerHTML = `<label for="name">Name</label><input id="name">`;
    const input = document.getElementById("name") as HTMLInputElement;
    input.addEventListener("input", () => {
      const current = input.value;
      input.value = "";
      setTimeout(() => {
        input.value = current;
      }, 10);
    }, { once: true });
    const question = scanDocument().questions[0]!;
    const result = await applyFillInstructions([{
      controlId: question.controlId,
      frameId: 0,
      value: "Aadil",
      sensitive: false,
      approved: true,
    }], { verificationTimeoutMs: 80, pollIntervalMs: 5 });
    expect(result[0]?.status).toBe("FILLED");
    expect(input.value).toBe("Aadil");
  });

  it("reports only whether a file has been selected, never its local path", () => {
    document.body.innerHTML = `<label for="resume">Resume</label><input id="resume" type="file" required>`;
    const control = scanDocument().controls.find((item) => item.kind === "FILE");
    expect(control).toBeDefined();
    expect(control?.fileSelected).toBe(false);
    expect(JSON.stringify(control)).not.toContain("fakepath");
  });
'''
if not fill_text.endswith(closing):
    raise SystemExit("fill.test.ts closing marker mismatch")
fill_test.write_text(
    fill_text[: -len(closing)] + fill_insert + closing,
    encoding="utf-8",
)
