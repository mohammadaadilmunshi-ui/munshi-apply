import {
  createAutoPilotSession,
  deriveApplicationIdentity,
  parseAutoPilotSession,
  planAutoPilotStep,
  prepareSessionCheckpoint,
  reduceAutoPilotSession,
  restoreSessionFromCheckpoint,
  verifyFillAction,
  type AutoPilotCheckpoint,
  type AutoPilotObservation,
  type AutoPilotSession,
  type PreflightGateSummary,
} from "@munshi-apply/application-model";
import type {
  ApplicationPage,
  FillInstruction,
  FillResult,
  NavigationCandidate,
} from "@munshi-apply/contracts";

export const AUTO_PILOT_RUNTIME_SCHEMA_VERSION = 1 as const;

export type AutoPilotWaitingFor = "FILL" | "NAVIGATION" | null;

export type AutoPilotRuntimeState = {
  schemaVersion: typeof AUTO_PILOT_RUNTIME_SCHEMA_VERSION;
  session: AutoPilotSession;
  tabId: number;
  lastUrl: string;
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
  waitingFor: AutoPilotWaitingFor;
  beforeNavigation: AutoPilotObservation | null;
  actionDeadlineAt: string | null;
  dispatchingFillControlId: string | null;
  navigationDispatchAttempted: boolean;
};

export type AutoPilotControllerStatus = {
  session: AutoPilotSession;
  tabId: number;
  lastUrl: string;
  waitingFor: AutoPilotWaitingFor;
  actionDeadlineAt: string | null;
};

export type AutoPilotStartInput = {
  tabId: number;
  applicationId: string;
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
};

export type AutoPilotResumeInput = {
  preflight: PreflightGateSummary;
  fillInstructions: readonly FillInstruction[];
};

export type NavigationResult = {
  status: "NAVIGATED" | "REFUSED" | "FAILED";
  reason: string;
};

export type NativeCheckpointSaveResult = {
  created: boolean;
  checkpoint: AutoPilotCheckpoint;
};

export type AutoPilotControllerDependencies = {
  loadRuntime: () => Promise<unknown>;
  saveRuntime: (state: AutoPilotRuntimeState | null) => Promise<void>;
  getPage: (tabId: number) => Promise<ApplicationPage | null>;
  fill: (tabId: number, instruction: FillInstruction) => Promise<FillResult[]>;
  navigate: (
    tabId: number,
    frameId: number,
    controlId: string,
  ) => Promise<NavigationResult>;
  ensureApplication: (
    applicationId: string,
    observedAt: string,
  ) => Promise<{ created: boolean }>;
  saveCheckpoint: (
    checkpoint: AutoPilotCheckpoint,
  ) => Promise<NativeCheckpointSaveResult>;
  getLatestCheckpoint: (
    applicationId: string,
  ) => Promise<AutoPilotCheckpoint | null>;
  now?: () => string;
  randomId?: () => string;
  scheduleTimeout?: (delayMilliseconds: number, callback: () => void) => void;
};

const FILL_TIMEOUT_MS = 5_000;
const NAVIGATION_TIMEOUT_MS = 12_000;
const validWaitingFor = new Set<AutoPilotWaitingFor>([
  null,
  "FILL",
  "NAVIGATION",
]);

function nowDefault(): string {
  return new Date().toISOString();
}

function randomIdDefault(): string {
  return crypto.randomUUID();
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function nullableString(value: unknown, name: string): string | null {
  if (value === null) return null;
  return requiredString(value, name);
}

function validTimestamp(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}T/.test(value) && !Number.isNaN(Date.parse(value));
}

function canonicalUrl(value: string): string {
  const url = new URL(value);
  url.hash = "";
  url.search = "";
  return url.href;
}

function parsePreflight(value: unknown): PreflightGateSummary {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("AutoPilot pre-flight state must be an object");
  }
  const candidate = value as Record<string, unknown>;
  if (!["READY", "REVIEW", "BLOCKED"].includes(String(candidate.state))) {
    throw new Error("AutoPilot pre-flight state is invalid");
  }
  for (const key of [
    "readyCount",
    "reviewCount",
    "unresolvedCount",
    "blockedCount",
  ] as const) {
    if (!Number.isSafeInteger(candidate[key]) || Number(candidate[key]) < 0) {
      throw new Error(`AutoPilot pre-flight ${key} must be non-negative`);
    }
  }
  if (typeof candidate.canAct !== "boolean") {
    throw new Error("AutoPilot pre-flight canAct must be boolean");
  }
  if ((candidate.state === "READY") !== candidate.canAct) {
    throw new Error("AutoPilot pre-flight canAct is inconsistent with state");
  }
  return {
    state: candidate.state as PreflightGateSummary["state"],
    readyCount: Number(candidate.readyCount),
    reviewCount: Number(candidate.reviewCount),
    unresolvedCount: Number(candidate.unresolvedCount),
    blockedCount: Number(candidate.blockedCount),
    canAct: candidate.canAct,
  };
}

function parseFillInstructions(value: unknown): FillInstruction[] {
  if (!Array.isArray(value)) {
    throw new Error("AutoPilot fill instructions must be an array");
  }
  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new Error("AutoPilot fill instruction must be an object");
    }
    const candidate = item as Record<string, unknown>;
    if (
      !Number.isSafeInteger(candidate.frameId) ||
      Number(candidate.frameId) < 0
    ) {
      throw new Error("AutoPilot fill frameId must be non-negative");
    }
    if (typeof candidate.value !== "string") {
      throw new Error("AutoPilot fill value must be a string");
    }
    if (
      typeof candidate.sensitive !== "boolean" ||
      typeof candidate.approved !== "boolean"
    ) {
      throw new Error("AutoPilot fill approval flags are invalid");
    }
    return {
      controlId: requiredString(candidate.controlId, "controlId"),
      frameId: Number(candidate.frameId),
      value: candidate.value,
      sensitive: candidate.sensitive,
      approved: candidate.approved,
    };
  });
}

function parseObservation(value: unknown): AutoPilotObservation | null {
  if (value === null) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("AutoPilot navigation observation must be an object");
  }
  const candidate = value as Record<string, unknown>;
  const visibleControlIds = candidate.visibleControlIds;
  if (!Array.isArray(visibleControlIds)) {
    throw new Error("AutoPilot visible controls must be an array");
  }
  const securityCheckpoint = candidate.securityCheckpoint;
  return {
    applicationId: requiredString(candidate.applicationId, "applicationId"),
    state: candidate.state as AutoPilotObservation["state"],
    pageId: requiredString(candidate.pageId, "pageId"),
    pageFingerprint: requiredString(
      candidate.pageFingerprint,
      "pageFingerprint",
    ),
    visibleControlIds: visibleControlIds.map((item) =>
      requiredString(item, "visibleControlId"),
    ),
    validationErrorCount: Number(candidate.validationErrorCount),
    securityCheckpoint:
      securityCheckpoint === null
        ? null
        : (requiredString(
            securityCheckpoint,
            "securityCheckpoint",
          ) as AutoPilotObservation["securityCheckpoint"]),
    canNavigateNext: Boolean(candidate.canNavigateNext),
    isFinalSubmissionStep: Boolean(candidate.isFinalSubmissionStep),
  };
}

export function parseAutoPilotRuntimeState(
  value: unknown,
): AutoPilotRuntimeState {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("AutoPilot runtime state must be an object");
  }
  const candidate = value as Record<string, unknown>;
  if (candidate.schemaVersion !== AUTO_PILOT_RUNTIME_SCHEMA_VERSION) {
    throw new Error("Unsupported AutoPilot runtime schema version");
  }
  if (!Number.isSafeInteger(candidate.tabId) || Number(candidate.tabId) < 0) {
    throw new Error("AutoPilot tabId must be a non-negative integer");
  }
  if (!validWaitingFor.has(candidate.waitingFor as AutoPilotWaitingFor)) {
    throw new Error("AutoPilot waiting state is invalid");
  }
  const lastUrl = requiredString(candidate.lastUrl, "lastUrl");
  new URL(lastUrl);
  const actionDeadlineAt = nullableString(
    candidate.actionDeadlineAt,
    "actionDeadlineAt",
  );
  if (actionDeadlineAt !== null && !validTimestamp(actionDeadlineAt)) {
    throw new Error("AutoPilot action deadline must be an ISO timestamp");
  }
  if (typeof candidate.navigationDispatchAttempted !== "boolean") {
    throw new Error("AutoPilot navigation dispatch marker is invalid");
  }

  return {
    schemaVersion: AUTO_PILOT_RUNTIME_SCHEMA_VERSION,
    session: parseAutoPilotSession(candidate.session),
    tabId: Number(candidate.tabId),
    lastUrl,
    preflight: parsePreflight(candidate.preflight),
    fillInstructions: parseFillInstructions(candidate.fillInstructions),
    waitingFor: candidate.waitingFor as AutoPilotWaitingFor,
    beforeNavigation: parseObservation(candidate.beforeNavigation),
    actionDeadlineAt,
    dispatchingFillControlId: nullableString(
      candidate.dispatchingFillControlId,
      "dispatchingFillControlId",
    ),
    navigationDispatchAttempted: candidate.navigationDispatchAttempted,
  };
}

function observationFor(
  runtime: AutoPilotRuntimeState,
  page: ApplicationPage,
): AutoPilotObservation {
  return {
    applicationId: runtime.session.applicationId,
    state: page.applicationState,
    pageId: page.pageId,
    pageFingerprint: page.pageFingerprint || page.pageId,
    visibleControlIds: page.controls
      .filter((control) => control.visible && !control.disabled)
      .map((control) => control.controlId),
    validationErrorCount: page.validationErrorCount,
    securityCheckpoint: page.securityCheckpoint,
    canNavigateNext: page.navigationCandidates.some(
      (candidate) =>
        !candidate.disabled &&
        (candidate.action === "NEXT" || candidate.action === "REVIEW"),
    ),
    isFinalSubmissionStep:
      page.finalSubmissionBoundary || page.applicationState === "SUBMISSION",
  };
}

function pendingControlIds(
  runtime: AutoPilotRuntimeState,
  completing?: string,
): string[] {
  const completed = new Set(runtime.session.completedControlIds);
  if (completing) completed.add(completing);
  return runtime.fillInstructions
    .filter((instruction) => instruction.approved)
    .map((instruction) => instruction.controlId)
    .filter((controlId) => !completed.has(controlId));
}

function checkpointEqual(
  left: AutoPilotCheckpoint,
  right: AutoPilotCheckpoint,
): boolean {
  return (
    left.checkpointId === right.checkpointId &&
    left.applicationId === right.applicationId &&
    left.sequence === right.sequence &&
    left.state === right.state &&
    left.pageId === right.pageId &&
    left.pageFingerprint === right.pageFingerprint &&
    JSON.stringify(left.completedControlIds) ===
      JSON.stringify(right.completedControlIds) &&
    JSON.stringify(left.pendingControlIds) ===
      JSON.stringify(right.pendingControlIds) &&
    left.selectedResumeId === right.selectedResumeId &&
    left.selectedResumeSha256 === right.selectedResumeSha256 &&
    left.createdAt === right.createdAt
  );
}

function navigationChanged(
  before: AutoPilotObservation,
  after: AutoPilotObservation,
): boolean {
  return (
    before.pageId !== after.pageId ||
    before.pageFingerprint !== after.pageFingerprint ||
    before.state !== after.state
  );
}

function safeForwardCandidate(
  page: ApplicationPage,
): NavigationCandidate | null {
  const candidates = page.navigationCandidates.filter(
    (candidate) =>
      !candidate.disabled &&
      (candidate.action === "NEXT" || candidate.action === "REVIEW"),
  );
  return candidates.length === 1 ? candidates[0]! : null;
}

export class AutoPilotController {
  private queue: Promise<void> = Promise.resolve();

  constructor(private readonly dependencies: AutoPilotControllerDependencies) {}

  private now(): string {
    return (this.dependencies.now ?? nowDefault)();
  }

  private randomId(): string {
    return (this.dependencies.randomId ?? randomIdDefault)();
  }

  private exclusive<T>(work: () => Promise<T>): Promise<T> {
    const run = this.queue.then(work, work);
    this.queue = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }

  private async load(): Promise<AutoPilotRuntimeState | null> {
    const candidate = await this.dependencies.loadRuntime();
    return candidate === null || candidate === undefined
      ? null
      : parseAutoPilotRuntimeState(candidate);
  }

  private async persist(
    runtime: AutoPilotRuntimeState | null,
  ): Promise<AutoPilotRuntimeState | null> {
    await this.dependencies.saveRuntime(runtime);
    return runtime;
  }

  private deadline(milliseconds: number): string {
    return new Date(Date.parse(this.now()) + milliseconds).toISOString();
  }

  private scheduleDeadline(milliseconds: number): void {
    this.dependencies.scheduleTimeout?.(milliseconds, () => {
      void this.checkTimeout();
    });
  }

  private async fail(
    runtime: AutoPilotRuntimeState,
    reason: string,
  ): Promise<AutoPilotRuntimeState> {
    const failed = parseAutoPilotRuntimeState({
      ...runtime,
      session: reduceAutoPilotSession(runtime.session, {
        type: "FAIL",
        reason,
        at: this.now(),
      }),
      waitingFor: null,
      beforeNavigation: null,
      actionDeadlineAt: null,
      dispatchingFillControlId: null,
      navigationDispatchAttempted: false,
    });
    await this.persist(failed);
    return failed;
  }

  private async saveCheckpointWithRetry(
    checkpoint: AutoPilotCheckpoint,
  ): Promise<NativeCheckpointSaveResult> {
    let firstError: unknown = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const result = await this.dependencies.saveCheckpoint(checkpoint);
        if (!checkpointEqual(result.checkpoint, checkpoint)) {
          throw new Error("Native checkpoint acknowledgement did not match");
        }
        return result;
      } catch (error) {
        firstError ??= error;
      }
    }
    throw firstError instanceof Error
      ? firstError
      : new Error("Native checkpoint save failed");
  }

  private async persistPause(
    runtime: AutoPilotRuntimeState,
    observation: AutoPilotObservation,
    action:
      | { type: "OWNER"; reason: string }
      | { type: "REVIEW"; reason: string }
      | {
          type: "SECURITY";
          checkpoint: NonNullable<AutoPilotObservation["securityCheckpoint"]>;
          reason: string;
        }
      | { type: "FINAL"; reason: string },
  ): Promise<AutoPilotRuntimeState> {
    const checkpoint = prepareSessionCheckpoint({
      session: runtime.session,
      checkpointId: `checkpoint-${this.randomId()}`,
      observation,
      createdAt: this.now(),
    });
    try {
      const saved = await this.saveCheckpointWithRetry(checkpoint);
      let session = reduceAutoPilotSession(runtime.session, {
        type: "CHECKPOINT_SAVED",
        checkpoint: saved.checkpoint,
        purpose: "PAUSE",
        at: this.now(),
      });
      if (action.type === "OWNER") {
        session = reduceAutoPilotSession(session, {
          type: "PAUSE_OWNER",
          reason: action.reason,
          at: this.now(),
        });
      } else if (action.type === "REVIEW") {
        session = reduceAutoPilotSession(session, {
          type: "PAUSE_REVIEW",
          reason: action.reason,
          at: this.now(),
        });
      } else if (action.type === "SECURITY") {
        session = reduceAutoPilotSession(session, {
          type: "PAUSE_SECURITY",
          checkpoint: action.checkpoint,
          reason: action.reason,
          at: this.now(),
        });
      } else {
        session = reduceAutoPilotSession(session, {
          type: "PAUSE_FINAL",
          reason: action.reason,
          at: this.now(),
        });
      }
      const paused = parseAutoPilotRuntimeState({
        ...runtime,
        session,
        waitingFor: null,
        beforeNavigation: null,
        actionDeadlineAt: null,
        dispatchingFillControlId: null,
        navigationDispatchAttempted: false,
      });
      await this.persist(paused);
      return paused;
    } catch (error) {
      return this.fail(
        runtime,
        `Unable to persist pause checkpoint: ${
          error instanceof Error ? error.message : "unknown error"
        }`,
      );
    }
  }

  private async dispatchNavigation(
    runtime: AutoPilotRuntimeState,
    page: ApplicationPage,
    candidate: NavigationCandidate,
  ): Promise<AutoPilotRuntimeState> {
    let current = parseAutoPilotRuntimeState({
      ...runtime,
      navigationDispatchAttempted: true,
      actionDeadlineAt: this.deadline(NAVIGATION_TIMEOUT_MS),
    });
    await this.persist(current);

    const result = await this.dependencies.navigate(
      current.tabId,
      candidate.frameId,
      candidate.controlId,
    );
    if (result.status !== "NAVIGATED") {
      return this.fail(
        current,
        `Navigation was not verified for dispatch: ${result.reason}`,
      );
    }

    current = parseAutoPilotRuntimeState({
      ...current,
      session: reduceAutoPilotSession(current.session, {
        type: "NAVIGATION_DISPATCHED",
        at: this.now(),
      }),
      waitingFor: "NAVIGATION",
      beforeNavigation: observationFor(current, page),
    });
    await this.persist(current);
    this.scheduleDeadline(NAVIGATION_TIMEOUT_MS);
    return current;
  }

  private async executeRunningStep(
    runtime: AutoPilotRuntimeState,
    page: ApplicationPage,
  ): Promise<AutoPilotRuntimeState> {
    if (runtime.session.status !== "RUNNING") return runtime;
    if (canonicalUrl(page.url) !== canonicalUrl(runtime.lastUrl)) {
      return this.fail(
        runtime,
        "Active tab changed to a different application URL without verified navigation",
      );
    }

    const observation = observationFor(runtime, page);
    const plan = planAutoPilotStep({
      observation,
      preflight: runtime.preflight,
      fillInstructions: runtime.fillInstructions,
      completedControlIds: runtime.session.completedControlIds,
    });

    switch (plan.action.type) {
      case "FILL": {
        const armed = parseAutoPilotRuntimeState({
          ...runtime,
          dispatchingFillControlId: plan.action.instruction.controlId,
          actionDeadlineAt: this.deadline(FILL_TIMEOUT_MS),
        });
        await this.persist(armed);

        let results: FillResult[];
        try {
          results = await this.dependencies.fill(
            armed.tabId,
            plan.action.instruction,
          );
        } catch (error) {
          return this.fail(
            armed,
            `Fill dispatch failed: ${
              error instanceof Error ? error.message : "unknown error"
            }`,
          );
        }
        const verification = verifyFillAction(
          plan.action.instruction.controlId,
          results,
        );
        if (!verification.success) {
          return this.fail(
            armed,
            `Fill verification failed: ${verification.reason}`,
          );
        }

        const waiting = parseAutoPilotRuntimeState({
          ...armed,
          session: reduceAutoPilotSession(armed.session, {
            type: "FILL_VERIFIED",
            controlId: plan.action.instruction.controlId,
            pendingControlIds: pendingControlIds(
              armed,
              plan.action.instruction.controlId,
            ),
            at: this.now(),
          }),
          waitingFor: "FILL",
          beforeNavigation: null,
          dispatchingFillControlId: null,
          actionDeadlineAt: this.deadline(FILL_TIMEOUT_MS),
        });
        await this.persist(waiting);
        this.scheduleDeadline(FILL_TIMEOUT_MS);
        return waiting;
      }

      case "NAVIGATE_NEXT": {
        const candidate = safeForwardCandidate(page);
        if (!candidate) {
          return this.fail(
            runtime,
            "Forward navigation is ambiguous or no longer available",
          );
        }
        const checkpoint = prepareSessionCheckpoint({
          session: runtime.session,
          checkpointId: `checkpoint-${this.randomId()}`,
          observation,
          createdAt: this.now(),
        });
        let saved: NativeCheckpointSaveResult;
        try {
          saved = await this.saveCheckpointWithRetry(checkpoint);
        } catch (error) {
          return this.fail(
            runtime,
            `Navigation checkpoint could not be persisted: ${
              error instanceof Error ? error.message : "unknown error"
            }`,
          );
        }

        const checkpointed = parseAutoPilotRuntimeState({
          ...runtime,
          session: reduceAutoPilotSession(runtime.session, {
            type: "CHECKPOINT_SAVED",
            checkpoint: saved.checkpoint,
            purpose: "NAVIGATION",
            at: this.now(),
          }),
          beforeNavigation: observation,
          navigationDispatchAttempted: false,
          actionDeadlineAt: this.deadline(NAVIGATION_TIMEOUT_MS),
        });
        await this.persist(checkpointed);
        return this.dispatchNavigation(checkpointed, page, candidate);
      }

      case "PAUSE_REVIEW":
        return this.persistPause(runtime, observation, {
          type: "REVIEW",
          reason: plan.action.reason,
        });

      case "PAUSE_SECURITY":
        return this.persistPause(runtime, observation, {
          type: "SECURITY",
          checkpoint: plan.action.checkpoint,
          reason: plan.reason,
        });

      case "PAUSE_FINAL_APPROVAL":
        return this.persistPause(runtime, observation, {
          type: "FINAL",
          reason: plan.reason,
        });

      case "WAIT":
        await this.persist(runtime);
        return runtime;
    }
  }

  private async startInternal(
    input: AutoPilotStartInput,
  ): Promise<AutoPilotControllerStatus> {
    if (!Number.isSafeInteger(input.tabId) || input.tabId < 0) {
      throw new Error("AutoPilot start requires a valid browser tab");
    }
    const applicationId = requiredString(input.applicationId, "applicationId");
    const preflight = parsePreflight(input.preflight);
    const instructions = parseFillInstructions(input.fillInstructions);
    const existing = await this.load();
    if (existing && existing.session.status !== "STOPPED") {
      throw new Error(
        "An AutoPilot session is already active; stop it before starting another",
      );
    }

    const page = await this.dependencies.getPage(input.tabId);
    if (!page) throw new Error("No active application page is available");

    await this.dependencies.ensureApplication(applicationId, page.observedAt);

    let session = createAutoPilotSession({
      sessionId: `session-${this.randomId()}`,
      applicationId,
      applicationIdentity: deriveApplicationIdentity({ url: page.url }),
      selectedResumeId: input.selectedResumeId,
      selectedResumeSha256: input.selectedResumeSha256,
      createdAt: this.now(),
    });
    session = parseAutoPilotSession({
      ...session,
      pendingControlIds: instructions
        .filter((instruction) => instruction.approved)
        .map((instruction) => instruction.controlId),
    });

    let runtime = parseAutoPilotRuntimeState({
      schemaVersion: AUTO_PILOT_RUNTIME_SCHEMA_VERSION,
      session,
      tabId: input.tabId,
      lastUrl: page.url,
      preflight,
      fillInstructions: instructions,
      waitingFor: null,
      beforeNavigation: null,
      actionDeadlineAt: null,
      dispatchingFillControlId: null,
      navigationDispatchAttempted: false,
    });
    const observation = observationFor(runtime, page);
    const latest = await this.dependencies.getLatestCheckpoint(applicationId);
    if (latest) {
      if (
        input.selectedResumeId !== null &&
        (latest.selectedResumeId !== input.selectedResumeId ||
          latest.selectedResumeSha256 !== input.selectedResumeSha256)
      ) {
        throw new Error(
          "Selected résumé does not match the durable application checkpoint",
        );
      }
      runtime = parseAutoPilotRuntimeState({
        ...runtime,
        session: restoreSessionFromCheckpoint({
          session: runtime.session,
          checkpoint: latest,
          observation,
          at: this.now(),
        }),
      });
    } else {
      runtime = parseAutoPilotRuntimeState({
        ...runtime,
        session: reduceAutoPilotSession(runtime.session, {
          type: "START",
          observation,
          at: this.now(),
        }),
      });
    }
    await this.persist(runtime);

    if (runtime.session.status === "PAUSED_SECURITY") {
      runtime = await this.persistPause(runtime, observation, {
        type: "SECURITY",
        checkpoint: runtime.session.securityCheckpoint!,
        reason:
          runtime.session.pauseReason ??
          "Browser security checkpoint requires owner action",
      });
    } else if (runtime.session.status === "PAUSED_FINAL") {
      runtime = await this.persistPause(runtime, observation, {
        type: "FINAL",
        reason:
          runtime.session.pauseReason ??
          "Final employer submission requires owner action",
      });
    } else if (runtime.session.status === "PAUSED_REVIEW") {
      runtime = await this.persistPause(runtime, observation, {
        type: "REVIEW",
        reason: runtime.session.pauseReason ?? "Owner review is required",
      });
    } else if (runtime.session.status === "RUNNING") {
      runtime = await this.executeRunningStep(runtime, page);
    }

    return this.statusFromRuntime(runtime);
  }

  private statusFromRuntime(
    runtime: AutoPilotRuntimeState,
  ): AutoPilotControllerStatus {
    return {
      session: runtime.session,
      tabId: runtime.tabId,
      lastUrl: runtime.lastUrl,
      waitingFor: runtime.waitingFor,
      actionDeadlineAt: runtime.actionDeadlineAt,
    };
  }

  async start(input: AutoPilotStartInput): Promise<AutoPilotControllerStatus> {
    return this.exclusive(() => this.startInternal(input));
  }

  async pause(
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
        throw new Error(
          "Application origin changed while AutoPilot was paused",
        );
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

  async stop(
    reason = "Stopped by owner",
  ): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      const runtime = await this.load();
      if (!runtime) return null;
      const stopped = parseAutoPilotRuntimeState({
        ...runtime,
        session: reduceAutoPilotSession(runtime.session, {
          type: "STOP",
          reason,
          at: this.now(),
        }),
        waitingFor: null,
        beforeNavigation: null,
        actionDeadlineAt: null,
        dispatchingFillControlId: null,
        navigationDispatchAttempted: false,
      });
      await this.persist(stopped);
      return this.statusFromRuntime(stopped);
    });
  }

  async status(): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      const runtime = await this.load();
      return runtime ? this.statusFromRuntime(runtime) : null;
    });
  }

  async onPageSnapshot(
    tabId: number,
    page: ApplicationPage,
  ): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      let runtime = await this.load();
      if (!runtime || runtime.tabId !== tabId) return null;
      if (
        runtime.session.status === "STOPPED" ||
        runtime.session.status.startsWith("PAUSED_")
      ) {
        return this.statusFromRuntime(runtime);
      }

      const after = observationFor(runtime, page);
      if (runtime.session.status === "WAITING_RESCAN") {
        if (runtime.waitingFor === "FILL") {
          if (canonicalUrl(page.url) !== canonicalUrl(runtime.lastUrl)) {
            runtime = await this.fail(
              runtime,
              "Application URL changed while waiting to verify a field fill",
            );
          } else {
            runtime = parseAutoPilotRuntimeState({
              ...runtime,
              session: reduceAutoPilotSession(runtime.session, {
                type: "RESCAN_VERIFIED",
                observation: after,
                at: this.now(),
              }),
              waitingFor: null,
              actionDeadlineAt: null,
              lastUrl: page.url,
            });
            await this.persist(runtime);
            if (runtime.session.status === "RUNNING") {
              runtime = await this.executeRunningStep(runtime, page);
            }
          }
        } else if (
          runtime.waitingFor === "NAVIGATION" &&
          runtime.beforeNavigation
        ) {
          if (!navigationChanged(runtime.beforeNavigation, after)) {
            return this.statusFromRuntime(runtime);
          }
          runtime = parseAutoPilotRuntimeState({
            ...runtime,
            session: reduceAutoPilotSession(runtime.session, {
              type: "NAVIGATION_VERIFIED",
              before: runtime.beforeNavigation,
              after,
              at: this.now(),
            }),
            waitingFor: null,
            beforeNavigation: null,
            actionDeadlineAt: null,
            navigationDispatchAttempted: false,
            lastUrl: page.url,
          });
          await this.persist(runtime);
          if (runtime.session.status === "RUNNING") {
            runtime = await this.executeRunningStep(runtime, page);
          }
        } else {
          runtime = await this.fail(
            runtime,
            "AutoPilot rescan state is missing its verification purpose",
          );
        }
      } else if (runtime.session.status === "RUNNING") {
        if (canonicalUrl(page.url) !== canonicalUrl(runtime.lastUrl)) {
          runtime = await this.fail(
            runtime,
            "Application page changed without a verified AutoPilot action",
          );
        }
      }

      return this.statusFromRuntime(runtime);
    });
  }

  private async recoverInternal(): Promise<AutoPilotControllerStatus | null> {
    let runtime = await this.load();
    if (!runtime) return null;
    if (
      runtime.session.status === "STOPPED" ||
      runtime.session.status.startsWith("PAUSED_")
    ) {
      return this.statusFromRuntime(runtime);
    }
    const page = await this.dependencies.getPage(runtime.tabId);
    if (!page) {
      runtime = await this.fail(
        runtime,
        "Unable to recover AutoPilot because the application tab is unavailable",
      );
      return this.statusFromRuntime(runtime);
    }

    await this.dependencies.ensureApplication(
      runtime.session.applicationId,
      page.observedAt,
    );

    if (runtime.dispatchingFillControlId) {
      runtime = await this.fail(
        runtime,
        "A field fill was interrupted before verification; owner review is required",
      );
      return this.statusFromRuntime(runtime);
    }

    const after = observationFor(runtime, page);
    if (runtime.session.status === "WAITING_NAVIGATION") {
      if (!runtime.beforeNavigation) {
        runtime = await this.fail(
          runtime,
          "Checkpointed navigation is missing its pre-navigation observation",
        );
        return this.statusFromRuntime(runtime);
      }
      if (navigationChanged(runtime.beforeNavigation, after)) {
        runtime = parseAutoPilotRuntimeState({
          ...runtime,
          session: reduceAutoPilotSession(runtime.session, {
            type: "NAVIGATION_DISPATCHED",
            at: this.now(),
          }),
          waitingFor: "NAVIGATION",
        });
        runtime = parseAutoPilotRuntimeState({
          ...runtime,
          session: reduceAutoPilotSession(runtime.session, {
            type: "NAVIGATION_VERIFIED",
            before: runtime.beforeNavigation!,
            after,
            at: this.now(),
          }),
          waitingFor: null,
          beforeNavigation: null,
          actionDeadlineAt: null,
          navigationDispatchAttempted: false,
          lastUrl: page.url,
        });
        await this.persist(runtime);
        if (runtime.session.status === "RUNNING") {
          runtime = await this.executeRunningStep(runtime, page);
        }
        return this.statusFromRuntime(runtime);
      }
      if (runtime.navigationDispatchAttempted) {
        if (
          runtime.actionDeadlineAt &&
          Date.parse(this.now()) >= Date.parse(runtime.actionDeadlineAt)
        ) {
          runtime = await this.fail(
            runtime,
            "Checkpointed navigation did not produce a verified page transition",
          );
        }
        return this.statusFromRuntime(runtime);
      }
      const candidate = safeForwardCandidate(page);
      if (!candidate) {
        runtime = await this.fail(
          runtime,
          "Checkpointed navigation can no longer identify one safe forward control",
        );
      } else {
        runtime = await this.dispatchNavigation(runtime, page, candidate);
      }
      return this.statusFromRuntime(runtime);
    }

    if (runtime.session.status === "WAITING_RESCAN") {
      if (runtime.waitingFor === "FILL") {
        if (
          Date.parse(page.observedAt) <= Date.parse(runtime.session.updatedAt)
        ) {
          if (
            runtime.actionDeadlineAt &&
            Date.parse(this.now()) >= Date.parse(runtime.actionDeadlineAt)
          ) {
            runtime = await this.fail(
              runtime,
              "AutoPilot did not receive a fresh post-fill page observation",
            );
          }
          return this.statusFromRuntime(runtime);
        }
        runtime = parseAutoPilotRuntimeState({
          ...runtime,
          session: reduceAutoPilotSession(runtime.session, {
            type: "RESCAN_VERIFIED",
            observation: after,
            at: this.now(),
          }),
          waitingFor: null,
          actionDeadlineAt: null,
          lastUrl: page.url,
        });
        await this.persist(runtime);
        if (runtime.session.status === "RUNNING") {
          runtime = await this.executeRunningStep(runtime, page);
        }
        return this.statusFromRuntime(runtime);
      }
      if (
        runtime.waitingFor === "NAVIGATION" &&
        runtime.beforeNavigation &&
        navigationChanged(runtime.beforeNavigation, after)
      ) {
        runtime = parseAutoPilotRuntimeState({
          ...runtime,
          session: reduceAutoPilotSession(runtime.session, {
            type: "NAVIGATION_VERIFIED",
            before: runtime.beforeNavigation,
            after,
            at: this.now(),
          }),
          waitingFor: null,
          beforeNavigation: null,
          actionDeadlineAt: null,
          navigationDispatchAttempted: false,
          lastUrl: page.url,
        });
        await this.persist(runtime);
        if (runtime.session.status === "RUNNING") {
          runtime = await this.executeRunningStep(runtime, page);
        }
        return this.statusFromRuntime(runtime);
      }
      if (
        runtime.actionDeadlineAt &&
        Date.parse(this.now()) >= Date.parse(runtime.actionDeadlineAt)
      ) {
        runtime = await this.fail(
          runtime,
          "AutoPilot action timed out before a verified rescan",
        );
      }
      return this.statusFromRuntime(runtime);
    }

    if (runtime.session.status === "RUNNING") {
      if (canonicalUrl(page.url) !== canonicalUrl(runtime.lastUrl)) {
        runtime = await this.fail(
          runtime,
          "Application URL changed while the service worker was suspended",
        );
      } else {
        runtime = await this.executeRunningStep(runtime, page);
      }
    }
    return this.statusFromRuntime(runtime);
  }

  async recover(): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(() => this.recoverInternal());
  }

  async checkTimeout(): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      let runtime = await this.load();
      if (
        !runtime ||
        !runtime.actionDeadlineAt ||
        runtime.session.status === "STOPPED" ||
        runtime.session.status.startsWith("PAUSED_")
      ) {
        return runtime ? this.statusFromRuntime(runtime) : null;
      }
      if (Date.parse(this.now()) < Date.parse(runtime.actionDeadlineAt)) {
        return this.statusFromRuntime(runtime);
      }
      runtime = await this.fail(
        runtime,
        "AutoPilot action timed out before verification",
      );
      return this.statusFromRuntime(runtime);
    });
  }
}
