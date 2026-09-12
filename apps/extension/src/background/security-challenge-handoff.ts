import {
  ApplicationPageSchema,
  type ApplicationPage,
  type SecurityCheckpointKind,
} from "@munshi-apply/contracts";
import type {
  AutoPilotRuntimeState,
  AutoPilotControllerStatus,
} from "./autopilot-controller";
import {
  decryptJson,
  fetchCloudEvents,
  getCloudConnection,
  getWorkspaceEncryptionKey,
  postEncryptedEntity,
  type CloudConnection,
  type CloudSyncEvent,
} from "../storage/cloud";

const RUNTIME_STORAGE_KEY = "autopilot-runtime-v1";
const ACTIVE_COMMAND_STORAGE_KEY = "security-challenge-active-command-v1";
const CONSUMED_COMMANDS_STORAGE_KEY = "security-challenge-consumed-commands-v1";
const COMMAND_ALARM = "munshi-security-challenge-command-poll-v1";
const COMMAND_POLL_MINUTES = 0.5;
const COMMAND_TTL_MS = 10 * 60 * 1000;
const CHALLENGE_TTL_MS = 45 * 60 * 1000;
const PAGE_SETTLE_MS = 175;
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
  | "SESSION_LOST"
  | "EXPIRED";

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

let processingCommands = false;
let resumeInFlight = false;

function nowIso(): string {
  return new Date().toISOString();
}

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isFresh(value: string, ttlMs: number): boolean {
  const age = Date.now() - timestampMs(value);
  return age >= 0 && age <= ttlMs;
}

function urlIdentity(value: string): string | null {
  try {
    const url = new URL(value);
    if (!/^https?:$/.test(url.protocol)) return null;
    url.hash = "";
    return `${url.origin}${url.pathname}${url.search}`;
  } catch {
    return null;
  }
}

function validCheckpoint(value: unknown): value is SecurityCheckpointKind {
  return typeof value === "string" && challengeKinds.has(value as SecurityCheckpointKind);
}

function challengeIdFor(runtime: RuntimeSnapshot, page: ApplicationPage): string {
  const checkpoint = runtime.session.securityCheckpoint ?? page.securityCheckpoint;
  return [
    "challenge",
    runtime.session.sessionId,
    page.pageId,
    checkpoint ?? "SECURITY",
  ].join(":");
}

async function loadRuntime(): Promise<RuntimeSnapshot | null> {
  const stored = await chrome.storage.session.get(RUNTIME_STORAGE_KEY);
  const value = stored[RUNTIME_STORAGE_KEY];
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as RuntimeSnapshot;
}

function latestEvent(
  events: CloudSyncEvent[],
  entityType: string,
  entityId: string,
): CloudSyncEvent | null {
  let latest: CloudSyncEvent | null = null;
  for (const event of events) {
    if (event.entityType !== entityType || event.entityId !== entityId) continue;
    if (!latest || event.sequence > latest.sequence) latest = event;
  }
  return latest;
}

async function upsertEncryptedState(input: {
  connection: CloudConnection;
  rawKey: string;
  events: CloudSyncEvent[];
  entityType: string;
  entityId: string;
  value: unknown;
}): Promise<void> {
  const latest = latestEvent(input.events, input.entityType, input.entityId);
  if (latest) {
    try {
      const previous = await decryptJson<unknown>(input.rawKey, latest.payloadCiphertext);
      if (JSON.stringify(previous) === JSON.stringify(input.value)) return;
    } catch {
      // A corrupt prior value must not prevent a fresh encrypted safety state.
    }
  }
  await postEncryptedEntity({
    connection: input.connection,
    rawKey: input.rawKey,
    entityType: input.entityType,
    entityId: input.entityId,
    baseVersion: latest ? latest.baseVersion + 1 : 0,
    value: input.value,
  });
}

async function cloudContext(): Promise<{
  connection: CloudConnection;
  rawKey: string;
  events: CloudSyncEvent[];
} | null> {
  const connection = await getCloudConnection();
  const rawKey = await getWorkspaceEncryptionKey();
  if (!connection || !rawKey) return null;
  const { events } = await fetchCloudEvents(connection, 0);
  return { connection, rawKey, events };
}

async function publishChallengeState(
  runtime: RuntimeSnapshot,
  page: ApplicationPage,
  status: ChallengeStateStatus,
  checkpointOverride?: SecurityCheckpointKind,
): Promise<void> {
  const context = await cloudContext();
  if (!context) return;
  const checkpoint =
    checkpointOverride ?? runtime.session.securityCheckpoint ?? page.securityCheckpoint;
  if (!checkpoint || !validCheckpoint(checkpoint)) return;
  const challengeId = challengeIdFor(runtime, page);
  const existingEvent = latestEvent(
    context.events,
    "SECURITY.CHALLENGE.STATE.V1",
    runtime.session.sessionId,
  );
  let detectedAt = runtime.session.updatedAt;
  if (existingEvent) {
    try {
      const existing = await decryptJson<Partial<ChallengeState>>(
        context.rawKey,
        existingEvent.payloadCiphertext,
      );
      if (existing.challengeId === challengeId && typeof existing.detectedAt === "string") {
        detectedAt = existing.detectedAt;
      }
    } catch {
      // Preserve the runtime timestamp if old state cannot be decrypted.
    }
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
    expiresAt: new Date(timestampMs(detectedAt) + CHALLENGE_TTL_MS).toISOString(),
    clearedAt: status === "CLEARED" ? updatedAt : null,
  };
  await upsertEncryptedState({
    ...context,
    entityType: "SECURITY.CHALLENGE.STATE.V1",
    entityId: runtime.session.sessionId,
    value: state,
  });
}

async function postAck(
  context: { connection: CloudConnection; rawKey: string; events: CloudSyncEvent[] },
  command: ChallengeCommand,
  status: ChallengeAckStatus,
  reason: string | null = null,
): Promise<void> {
  const ack: ChallengeAck = {
    schemaVersion: 1,
    commandId: command.commandId,
    challengeId: command.challengeId,
    deviceId: context.connection.deviceId,
    status,
    reason,
    updatedAt: nowIso(),
  };
  await upsertEncryptedState({
    ...context,
    entityType: "SECURITY.CHALLENGE.ACK.V1",
    entityId: command.commandId,
    value: ack,
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
    !validCheckpoint(candidate.expectedCheckpoint) ||
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
  const next = [commandId, ...previous.filter((item) => item !== commandId)].slice(
    0,
    MAX_CONSUMED_COMMANDS,
  );
  await chrome.storage.local.set({ [CONSUMED_COMMANDS_STORAGE_KEY]: next });
}

async function focusCommand(command: ChallengeCommand): Promise<void> {
  if (processingCommands) return;
  processingCommands = true;
  try {
    const context = await cloudContext();
    if (!context || command.targetDeviceId !== context.connection.deviceId) return;
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
      await postAck(context, command, "STALE_SESSION", "The saved AutoPilot security pause no longer matches this command.");
      await rememberConsumed(command.commandId);
      return;
    }
    if (!isFresh(command.createdAt, COMMAND_TTL_MS) || Date.now() > timestampMs(command.expiresAt)) {
      await postAck(context, command, "REJECTED", "The focus request expired before Chromium received it.");
      await rememberConsumed(command.commandId);
      return;
    }
    const tab = await chrome.tabs.get(command.tabId).catch(() => null);
    if (!tab || tab.id === undefined || !tab.url) {
      await postAck(context, command, "SESSION_LOST", "The original Chromium application tab is no longer available.");
      await rememberConsumed(command.commandId);
      return;
    }
    if (urlIdentity(tab.url) !== urlIdentity(command.url)) {
      await postAck(context, command, "SESSION_LOST", "The saved Chromium tab moved to a different application page.");
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
  } finally {
    processingCommands = false;
  }
}

async function processCloudCommands(): Promise<void> {
  if (processingCommands) return;
  const context = await cloudContext();
  if (!context) return;
  const consumed = new Set(await consumedCommands());
  const commands: ChallengeCommand[] = [];
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
        commands.push(command);
      }
    } catch {
      // Malformed or undecryptable commands are ignored rather than executed.
    }
  }
  commands.sort((left, right) => right.createdAt.localeCompare(left.createdAt));
  const newest = commands[0];
  if (newest) await focusCommand(newest);
}

async function activeCommand(
  context: { connection: CloudConnection; rawKey: string; events: CloudSyncEvent[] },
): Promise<ChallengeCommand | null> {
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
    return parseCommand(await decryptJson<unknown>(context.rawKey, event.payloadCiphertext));
  } catch {
    return null;
  }
}

async function resumeAfterVerifiedClearance(
  runtime: RuntimeSnapshot,
  page: ApplicationPage,
): Promise<void> {
  if (resumeInFlight) return;
  resumeInFlight = true;
  const previousCheckpoint = runtime.session.securityCheckpoint;
  try {
    if (
      runtime.session.status !== "PAUSED_SECURITY" ||
      !previousCheckpoint ||
      page.securityCheckpoint !== null ||
      runtime.tabId !== page.tabId ||
      runtime.session.lastPageId !== page.pageId ||
      urlIdentity(runtime.lastUrl) !== urlIdentity(page.url) ||
      timestampMs(page.observedAt) <= timestampMs(runtime.session.updatedAt)
    ) {
      return;
    }

    await publishChallengeState(runtime, page, "VERIFYING", previousCheckpoint);
    const response = (await chrome.runtime.sendMessage({
      type: "AUTOPILOT_RESUME",
      payload: {
        preflight: runtime.preflight,
        fillInstructions: runtime.fillInstructions,
      },
    })) as { ok?: boolean; data?: AutoPilotControllerStatus; error?: string } | undefined;

    const context = await cloudContext();
    if (!response?.ok || !response.data) {
      if (context) {
        const command = await activeCommand(context);
        if (command) {
          await postAck(
            context,
            command,
            "RESUME_BLOCKED",
            response?.error ?? "AutoPilot did not acknowledge the verified security clearance.",
          );
        }
      }
      return;
    }
    if (response.data.session.status === "PAUSED_SECURITY") return;
    await publishChallengeState(runtime, page, "CLEARED", previousCheckpoint);
    if (context) {
      const command = await activeCommand(context);
      if (command) await postAck(context, command, "CLEARED_AND_RESUMED");
    }
    await chrome.storage.session.remove(ACTIVE_COMMAND_STORAGE_KEY);
  } finally {
    resumeInFlight = false;
  }
}

async function synchronizeChallengeFromPage(page: ApplicationPage): Promise<void> {
  const runtime = await loadRuntime();
  if (!runtime || runtime.tabId !== page.tabId) return;
  if (runtime.session.status !== "PAUSED_SECURITY") return;

  const checkpoint = runtime.session.securityCheckpoint;
  if (checkpoint && page.securityCheckpoint) {
    if (page.securityCheckpoint !== checkpoint) return;
    await publishChallengeState(runtime, page, "WAITING_FOR_USER", checkpoint);
    return;
  }
  if (checkpoint && page.securityCheckpoint === null) {
    await resumeAfterVerifiedClearance(runtime, page);
  }
}

async function synchronizeCurrentPausedSession(): Promise<void> {
  const runtime = await loadRuntime();
  if (!runtime || runtime.session.status !== "PAUSED_SECURITY") return;
  const tab = await chrome.tabs.get(runtime.tabId).catch(() => null);
  if (!tab || tab.id === undefined || !tab.url) {
    const context = await cloudContext();
    if (!context || !runtime.session.securityCheckpoint) return;
    const state: ChallengeState = {
      schemaVersion: 1,
      challengeId: [
        "challenge",
        runtime.session.sessionId,
        runtime.session.lastPageId ?? "missing-page",
        runtime.session.securityCheckpoint,
      ].join(":"),
      sessionId: runtime.session.sessionId,
      applicationId: runtime.session.applicationId,
      pageId: runtime.session.lastPageId ?? "missing-page",
      tabId: runtime.tabId,
      deviceId: context.connection.deviceId,
      url: runtime.lastUrl,
      title: "Application verification",
      pageFingerprint: runtime.session.lastPageFingerprint ?? "",
      checkpoint: runtime.session.securityCheckpoint,
      status: "SESSION_LOST",
      detectedAt: runtime.session.updatedAt,
      updatedAt: nowIso(),
      expiresAt: new Date(timestampMs(runtime.session.updatedAt) + CHALLENGE_TTL_MS).toISOString(),
      clearedAt: null,
    };
    await upsertEncryptedState({
      ...context,
      entityType: "SECURITY.CHALLENGE.STATE.V1",
      entityId: runtime.session.sessionId,
      value: state,
    });
  }
}

function install(): void {
  try {
    chrome.alarms.create(COMMAND_ALARM, { periodInMinutes: COMMAND_POLL_MINUTES });
  } catch {
    // Older Chromium builds may reject alarm registration before extension startup.
  }

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
    const parsed = ApplicationPageSchema.safeParse(
      (message as { payload?: unknown }).payload,
    );
    if (!parsed.success || parsed.data.tabId !== sender.tab.id) return undefined;
    globalThis.setTimeout(() => {
      void synchronizeChallengeFromPage(parsed.data).catch(() => undefined);
    }, PAGE_SETTLE_MS);
    return undefined;
  });

  void Promise.all([
    processCloudCommands(),
    synchronizeCurrentPausedSession(),
  ]).catch(() => undefined);
}

install();
