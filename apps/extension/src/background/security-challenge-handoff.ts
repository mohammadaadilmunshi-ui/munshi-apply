import type {
  ApplicationPage,
  SecurityCheckpointKind,
} from "@munshi-apply/contracts";
import type {
  AutoPilotControllerStatus,
  AutoPilotRuntimeState,
} from "./autopilot-controller";
import { mergeApplicationPages } from "./page-merge";
import {
  decryptJson,
  fetchCloudEvents,
  getCloudConnection,
  getWorkspaceEncryptionKey,
  postEncryptedEntity,
  type CloudConnection,
  type CloudSyncEvent,
} from "../storage/cloud";
import { getPagesForTab } from "../storage/vault";

const RUNTIME_STORAGE_KEY = "autopilot-runtime-v1";
const ACTIVE_COMMAND_STORAGE_KEY = "security-challenge-active-command-v1";
const CONSUMED_COMMANDS_STORAGE_KEY = "security-challenge-consumed-commands-v1";
const COMMAND_ALARM = "munshi-security-challenge-command-poll-v1";
const COMMAND_POLL_MINUTES = 0.5;
const COMMAND_TTL_MS = 10 * 60 * 1000;
const CHALLENGE_TTL_MS = 45 * 60 * 1000;
const PAGE_SETTLE_MS = 225;
const MAX_CONSUMED_COMMANDS = 64;

const challengeKinds = new Set<SecurityCheckpointKind>([
  "CAPTCHA",
  "MFA",
  "OTP",
  "IDENTITY_VERIFICATION",
  "AUTHENTICATION",
]);

type ChallengeStateStatus =
  | "WAITING_FOR_USER"
  | "VERIFYING"
  | "CLEARED"
  | "SESSION_LOST";

type ChallengeState = {
  schemaVersion: 1;
  challengeId: string;
  sessionId: string;
  applicationId: string;
  pageId: string;
  tabId: number;
  deviceId: string;
  url: string;
  title: string;
  pageFingerprint: string;
  checkpoint: SecurityCheckpointKind;
  status: ChallengeStateStatus;
  detectedAt: string;
  updatedAt: string;
  expiresAt: string;
  clearedAt: string | null;
};

type ChallengeCommand = {
  schemaVersion: 1;
  commandId: string;
  challengeId: string;
  action: "FOCUS_AND_CONTINUE";
  targetDeviceId: string;
  sessionId: string;
  applicationId: string;
  pageId: string;
  tabId: number;
  url: string;
  pageFingerprint: string;
  expectedCheckpoint: SecurityCheckpointKind;
  createdAt: string;
  expiresAt: string;
};

type ChallengeAckStatus =
  | "FOCUSED"
  | "REJECTED"
  | "STALE_SESSION"
  | "SESSION_LOST"
  | "CLEARED_AND_RESUMED"
  | "RESUME_BLOCKED";

type ChallengeAck = {
  schemaVersion: 1;
  commandId: string;
  challengeId: string;
  deviceId: string;
  status: ChallengeAckStatus;
  reason: string | null;
  updatedAt: string;
};

type RuntimeSnapshot = AutoPilotRuntimeState & {
  session: AutoPilotRuntimeState["session"] & {
    status: string;
    securityCheckpoint: SecurityCheckpointKind | null;
  };
};

type CloudContext = {
  connection: CloudConnection;
  rawKey: string;
  events: CloudSyncEvent[];
};

let commandPollInFlight = false;
let resumeInFlight = false;

function nowIso(): string {
  return new Date().toISOString();
}

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function urlIdentity(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    url.hash = "";
    return `${url.origin}${url.pathname}${url.search}`;
  } catch {
    return null;
  }
}

function isCheckpoint(value: unknown): value is SecurityCheckpointKind {
  return (
    typeof value === "string" &&
    challengeKinds.has(value as SecurityCheckpointKind)
  );
}

function challengeIdFor(
  runtime: RuntimeSnapshot,
  page: ApplicationPage,
  checkpoint: SecurityCheckpointKind,
): string {
  return ["challenge", runtime.session.sessionId, page.pageId, checkpoint].join(
    ":",
  );
}

async function loadRuntime(): Promise<RuntimeSnapshot | null> {
  const stored = await chrome.storage.session.get(RUNTIME_STORAGE_KEY);
  const candidate = stored[RUNTIME_STORAGE_KEY];
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return null;
  }
  return candidate as RuntimeSnapshot;
}

async function mergedPage(tabId: number): Promise<ApplicationPage | null> {
  return mergeApplicationPages(await getPagesForTab(tabId));
}

function latestEvent(
  events: CloudSyncEvent[],
  entityType: string,
  entityId: string,
): CloudSyncEvent | null {
  let selected: CloudSyncEvent | null = null;
  for (const event of events) {
    if (event.entityType !== entityType || event.entityId !== entityId) continue;
    if (!selected || event.sequence > selected.sequence) selected = event;
  }
  return selected;
}

async function cloudContext(): Promise<CloudContext | null> {
  const connection = await getCloudConnection();
  const rawKey = await getWorkspaceEncryptionKey();
  if (!connection || !rawKey) return null;
  const { events } = await fetchCloudEvents(connection, 0);
  return { connection, rawKey, events };
}

async function upsertEncrypted(input: {
  context: CloudContext;
  entityType: string;
  entityId: string;
  value: unknown;
}): Promise<void> {
  const previous = latestEvent(
    input.context.events,
    input.entityType,
    input.entityId,
  );
  await postEncryptedEntity({
    connection: input.context.connection,
    rawKey: input.context.rawKey,
    entityType: input.entityType,
    entityId: input.entityId,
    baseVersion: previous ? previous.baseVersion + 1 : 0,
    value: input.value,
  });
}

async function previousChallengeState(
  context: CloudContext,
  sessionId: string,
): Promise<ChallengeState | null> {
  const event = latestEvent(
    context.events,
    "SECURITY.CHALLENGE.STATE.V1",
    sessionId,
  );
  if (!event) return null;
  try {
    const candidate = await decryptJson<ChallengeState>(
      context.rawKey,
      event.payloadCiphertext,
    );
    return candidate?.schemaVersion === 1 ? candidate : null;
  } catch {
    return null;
  }
}

async function publishChallengeState(
  runtime: RuntimeSnapshot,
  page: ApplicationPage,
  checkpoint: SecurityCheckpointKind,
  status: ChallengeStateStatus,
): Promise<void> {
  const context = await cloudContext();
  if (!context) return;
  const challengeId = challengeIdFor(runtime, page, checkpoint);
  const previous = await previousChallengeState(context, runtime.session.sessionId);
  const detectedAt =
    previous?.challengeId === challengeId
      ? previous.detectedAt
      : runtime.session.updatedAt;

  if (
    previous?.challengeId === challengeId &&
    previous.status === status &&
    previous.url === page.url &&
    previous.pageFingerprint === page.pageFingerprint &&
    previous.checkpoint === checkpoint
  ) {
    return;
  }

  const updatedAt = nowIso();
  const state: ChallengeState = {
    schemaVersion: 1,
    challengeId,
    sessionId: runtime.session.sessionId,
    applicationId: runtime.session.applicationId,
    pageId: page.pageId,
    tabId: runtime.tabId,
    deviceId: context.connection.deviceId,
    url: page.url,
    title: page.title,
    pageFingerprint: page.pageFingerprint,
    checkpoint,
    status,
    detectedAt,
    updatedAt,
    expiresAt: new Date(
      Math.max(timestampMs(detectedAt), Date.now()) + CHALLENGE_TTL_MS,
    ).toISOString(),
    clearedAt: status === "CLEARED" ? updatedAt : null,
  };
  await upsertEncrypted({
    context,
    entityType: "SECURITY.CHALLENGE.STATE.V1",
    entityId: runtime.session.sessionId,
    value: state,
  });
}

async function publishSessionLost(runtime: RuntimeSnapshot): Promise<void> {
  const checkpoint = runtime.session.securityCheckpoint;
  if (!checkpoint) return;
  const context = await cloudContext();
  if (!context) return;
  const previous = await previousChallengeState(context, runtime.session.sessionId);
  if (previous?.status === "SESSION_LOST") return;
  const updatedAt = nowIso();
  const state: ChallengeState = {
    schemaVersion: 1,
    challengeId:
      previous?.challengeId ??
      [
        "challenge",
        runtime.session.sessionId,
        runtime.session.lastPageId ?? "missing-page",
        checkpoint,
      ].join(":"),
    sessionId: runtime.session.sessionId,
    applicationId: runtime.session.applicationId,
    pageId: runtime.session.lastPageId ?? "missing-page",
    tabId: runtime.tabId,
    deviceId: context.connection.deviceId,
    url: runtime.lastUrl,
    title: previous?.title ?? "Application verification",
    pageFingerprint: runtime.session.lastPageFingerprint ?? "",
    checkpoint,
    status: "SESSION_LOST",
    detectedAt: previous?.detectedAt ?? runtime.session.updatedAt,
    updatedAt,
    expiresAt: new Date(Date.now() + CHALLENGE_TTL_MS).toISOString(),
    clearedAt: null,
  };
  await upsertEncrypted({
    context,
    entityType: "SECURITY.CHALLENGE.STATE.V1",
    entityId: runtime.session.sessionId,
    value: state,
  });
}

function parseCommand(value: unknown): ChallengeCommand | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Partial<ChallengeCommand>;
  if (
    candidate.schemaVersion !== 1 ||
    candidate.action !== "FOCUS_AND_CONTINUE" ||
    typeof candidate.commandId !== "string" ||
    typeof candidate.challengeId !== "string" ||
    typeof candidate.targetDeviceId !== "string" ||
    typeof candidate.sessionId !== "string" ||
    typeof candidate.applicationId !== "string" ||
    typeof candidate.pageId !== "string" ||
    !Number.isSafeInteger(candidate.tabId) ||
    typeof candidate.url !== "string" ||
    typeof candidate.pageFingerprint !== "string" ||
    !isCheckpoint(candidate.expectedCheckpoint) ||
    typeof candidate.createdAt !== "string" ||
    typeof candidate.expiresAt !== "string"
  ) {
    return null;
  }
  return candidate as ChallengeCommand;
}

async function consumedCommands(): Promise<string[]> {
  const stored = await chrome.storage.local.get(CONSUMED_COMMANDS_STORAGE_KEY);
  const value = stored[CONSUMED_COMMANDS_STORAGE_KEY];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

async function rememberConsumed(commandId: string): Promise<void> {
  const previous = await consumedCommands();
  await chrome.storage.local.set({
    [CONSUMED_COMMANDS_STORAGE_KEY]: [
      commandId,
      ...previous.filter((item) => item !== commandId),
    ].slice(0, MAX_CONSUMED_COMMANDS),
  });
}

async function postAck(
  context: CloudContext,
  command: ChallengeCommand,
  status: ChallengeAckStatus,
  reason: string | null = null,
): Promise<void> {
  const value: ChallengeAck = {
    schemaVersion: 1,
    commandId: command.commandId,
    challengeId: command.challengeId,
    deviceId: context.connection.deviceId,
    status,
    reason,
    updatedAt: nowIso(),
  };
  const freshContext = (await cloudContext()) ?? context;
  await upsertEncrypted({
    context: freshContext,
    entityType: "SECURITY.CHALLENGE.ACK.V1",
    entityId: command.commandId,
    value,
  });
}

async function activeCommand(context: CloudContext): Promise<ChallengeCommand | null> {
  const stored = await chrome.storage.session.get(ACTIVE_COMMAND_STORAGE_KEY);
  const commandId = stored[ACTIVE_COMMAND_STORAGE_KEY];
  if (typeof commandId !== "string") return null;
  const event = latestEvent(
    context.events,
    "SECURITY.CHALLENGE.COMMAND.V1",
    commandId,
  );
  if (!event) return null;
  try {
    return parseCommand(
      await decryptJson<unknown>(context.rawKey, event.payloadCiphertext),
    );
  } catch {
    return null;
  }
}

async function focusCommand(
  context: CloudContext,
  command: ChallengeCommand,
): Promise<void> {
  const runtime = await loadRuntime();
  if (
    !runtime ||
    runtime.session.status !== "PAUSED_SECURITY" ||
    runtime.session.sessionId !== command.sessionId ||
    runtime.session.applicationId !== command.applicationId ||
    runtime.tabId !== command.tabId ||
    runtime.session.lastPageId !== command.pageId ||
    runtime.session.securityCheckpoint !== command.expectedCheckpoint
  ) {
    await postAck(
      context,
      command,
      "STALE_SESSION",
      "The saved AutoPilot security pause no longer matches this continuation request.",
    );
    await rememberConsumed(command.commandId);
    return;
  }
  const createdAt = timestampMs(command.createdAt);
  const expiresAt = timestampMs(command.expiresAt);
  if (
    createdAt <= 0 ||
    expiresAt <= Date.now() ||
    Date.now() - createdAt > COMMAND_TTL_MS
  ) {
    await postAck(
      context,
      command,
      "REJECTED",
      "The continuation request expired before Chromium received it.",
    );
    await rememberConsumed(command.commandId);
    return;
  }

  const tab = await chrome.tabs.get(command.tabId).catch(() => null);
  if (!tab || tab.id === undefined || !tab.url) {
    await postAck(
      context,
      command,
      "SESSION_LOST",
      "The original Chromium application tab is no longer available.",
    );
    await rememberConsumed(command.commandId);
    return;
  }
  if (urlIdentity(tab.url) !== urlIdentity(command.url)) {
    await postAck(
      context,
      command,
      "SESSION_LOST",
      "The saved Chromium tab moved to a different application page.",
    );
    await rememberConsumed(command.commandId);
    return;
  }

  if (tab.windowId !== undefined) {
    await chrome.windows.update(tab.windowId, { focused: true });
  }
  await chrome.tabs.update(command.tabId, { active: true });
  await chrome.storage.session.set({
    [ACTIVE_COMMAND_STORAGE_KEY]: command.commandId,
  });
  await postAck(context, command, "FOCUSED");
  await rememberConsumed(command.commandId);
}

async function processCloudCommands(): Promise<void> {
  if (commandPollInFlight) return;
  commandPollInFlight = true;
  try {
    const context = await cloudContext();
    if (!context) return;
    const consumed = new Set(await consumedCommands());
    const candidates: ChallengeCommand[] = [];
    for (const event of context.events) {
      if (event.entityType !== "SECURITY.CHALLENGE.COMMAND.V1") continue;
      try {
        const command = parseCommand(
          await decryptJson<unknown>(context.rawKey, event.payloadCiphertext),
        );
        if (
          command &&
          command.targetDeviceId === context.connection.deviceId &&
          !consumed.has(command.commandId)
        ) {
          candidates.push(command);
        }
      } catch {
        // Undecryptable commands are ignored rather than executed.
      }
    }
    candidates.sort((left, right) => right.createdAt.localeCompare(left.createdAt));
    if (candidates[0]) await focusCommand(context, candidates[0]);
  } finally {
    commandPollInFlight = false;
  }
}

async function resumeAfterVerifiedClearance(
  runtime: RuntimeSnapshot,
  page: ApplicationPage,
): Promise<void> {
  if (resumeInFlight) return;
  const checkpoint = runtime.session.securityCheckpoint;
  if (
    runtime.session.status !== "PAUSED_SECURITY" ||
    !checkpoint ||
    page.securityCheckpoint !== null ||
    runtime.tabId !== page.tabId ||
    runtime.session.lastPageId !== page.pageId ||
    urlIdentity(runtime.lastUrl) !== urlIdentity(page.url) ||
    timestampMs(page.observedAt) <= timestampMs(runtime.session.updatedAt)
  ) {
    return;
  }

  resumeInFlight = true;
  try {
    await publishChallengeState(runtime, page, checkpoint, "VERIFYING");
    const response = (await chrome.runtime.sendMessage({
      type: "AUTOPILOT_RESUME",
      payload: {
        preflight: runtime.preflight,
        fillInstructions: runtime.fillInstructions,
      },
    })) as
      | {
          ok?: boolean;
          data?: AutoPilotControllerStatus;
          error?: string;
        }
      | undefined;

    const context = await cloudContext();
    const command = context ? await activeCommand(context) : null;
    if (!response?.ok || !response.data) {
      if (context && command) {
        await postAck(
          context,
          command,
          "RESUME_BLOCKED",
          response?.error ??
            "AutoPilot did not acknowledge the verified security clearance.",
        );
      }
      return;
    }
    if (response.data.session.status === "PAUSED_SECURITY") return;

    await publishChallengeState(runtime, page, checkpoint, "CLEARED");
    if (context && command) {
      await postAck(context, command, "CLEARED_AND_RESUMED");
    }
    await chrome.storage.session.remove(ACTIVE_COMMAND_STORAGE_KEY);
  } finally {
    resumeInFlight = false;
  }
}

async function synchronizePausedPage(page: ApplicationPage): Promise<void> {
  const runtime = await loadRuntime();
  if (
    !runtime ||
    runtime.session.status !== "PAUSED_SECURITY" ||
    runtime.tabId !== page.tabId
  ) {
    return;
  }
  const checkpoint = runtime.session.securityCheckpoint;
  if (!checkpoint) return;

  if (page.securityCheckpoint === checkpoint) {
    await publishChallengeState(
      runtime,
      page,
      checkpoint,
      "WAITING_FOR_USER",
    );
    return;
  }
  if (page.securityCheckpoint === null) {
    await resumeAfterVerifiedClearance(runtime, page);
  }
}

async function synchronizeCurrentPausedSession(): Promise<void> {
  const runtime = await loadRuntime();
  if (!runtime || runtime.session.status !== "PAUSED_SECURITY") return;
  const tab = await chrome.tabs.get(runtime.tabId).catch(() => null);
  if (!tab || tab.id === undefined || !tab.url) {
    await publishSessionLost(runtime);
    return;
  }
  const page = await mergedPage(runtime.tabId);
  if (page) await synchronizePausedPage(page);
}

function install(): void {
  chrome.alarms.create(COMMAND_ALARM, {
    periodInMinutes: COMMAND_POLL_MINUTES,
  });

  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name !== COMMAND_ALARM) return;
    void Promise.all([
      processCloudCommands(),
      synchronizeCurrentPausedSession(),
    ]).catch(() => undefined);
  });

  chrome.runtime.onMessage.addListener((message: unknown, sender) => {
    if (
      !message ||
      typeof message !== "object" ||
      Array.isArray(message) ||
      (message as { type?: unknown }).type !== "PAGE_SNAPSHOT" ||
      sender.tab?.id === undefined
    ) {
      return undefined;
    }
    const tabId = sender.tab.id;
    globalThis.setTimeout(() => {
      void mergedPage(tabId)
        .then((page) => (page ? synchronizePausedPage(page) : undefined))
        .catch(() => undefined);
    }, PAGE_SETTLE_MS);
    return undefined;
  });

  void Promise.all([
    processCloudCommands(),
    synchronizeCurrentPausedSession(),
  ]).catch(() => undefined);
}

install();
