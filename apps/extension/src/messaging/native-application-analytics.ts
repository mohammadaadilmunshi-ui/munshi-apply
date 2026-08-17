import {
  summarizeApplicationAnalytics,
  type ApplicationAttributionContext,
  type ApplicationFunnelSummary,
  type ApplicationLifecycleEvent,
  type ApplicationLifecycleEventType,
  type ApplicationOutcomeEvent,
  type ApplicationOutcomeStage,
} from "@munshi-apply/application-model";

const nativeHostName = "systems.munshi.apply";
const lifecycleTypes = new Set<ApplicationLifecycleEventType>([
  "DETECTED",
  "PREPARED",
  "AUTOPILOT_STARTED",
  "AUTOPILOT_COMPLETED",
  "AUTOPILOT_PAUSED",
  "AUTOPILOT_FAILED",
  "DRAFT_USED",
  "RESUME_USED",
  "RECRUITER_RESPONSE",
]);
const outcomeStages = new Set<ApplicationOutcomeStage>([
  "APPLIED",
  "ASSESSMENT",
  "INTERVIEW",
  "OFFER",
  "REJECTED",
  "WITHDRAWN",
]);

type NativeResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };

export type NativeApplicationAnalyticsSnapshot = {
  contexts: ApplicationAttributionContext[];
  lifecycleEvents: ApplicationLifecycleEvent[];
  outcomes: ApplicationOutcomeEvent[];
};

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value.trim();
}

function optionalString(value: unknown, label: string): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string")
    throw new Error(`${label} must be a string or null`);
  return value.trim() || null;
}

function timestamp(value: unknown, label: string): string {
  const result = requiredString(value, label);
  if (
    Number.isNaN(Date.parse(result)) ||
    !/(?:Z|[+-]\d{2}:\d{2})$/i.test(result)
  ) {
    throw new Error(`${label} must be a timezone-aware ISO timestamp`);
  }
  return result;
}

function parseContext(value: unknown): ApplicationAttributionContext {
  const item = objectValue(value, "Attribution context");
  return {
    applicationId: requiredString(
      item.applicationId,
      "Attribution applicationId",
    ),
    capturedAt: timestamp(item.capturedAt, "Attribution capturedAt"),
    jobSource: optionalString(item.jobSource, "Attribution jobSource"),
    atsFamily: optionalString(item.atsFamily, "Attribution atsFamily"),
    resumeId: optionalString(item.resumeId, "Attribution resumeId"),
  };
}

function parseLifecycleEvent(value: unknown): ApplicationLifecycleEvent {
  const item = objectValue(value, "Application lifecycle event");
  const eventType = requiredString(
    item.eventType,
    "Application lifecycle eventType",
  ) as ApplicationLifecycleEventType;
  if (!lifecycleTypes.has(eventType)) {
    throw new Error("Application lifecycle eventType is invalid");
  }
  const metadata = item.metadata;
  if (
    metadata !== undefined &&
    (!metadata || typeof metadata !== "object" || Array.isArray(metadata))
  ) {
    throw new Error("Application lifecycle metadata must be an object");
  }
  return {
    eventId: requiredString(item.eventId, "Application lifecycle eventId"),
    applicationId: requiredString(
      item.applicationId,
      "Application lifecycle applicationId",
    ),
    eventType,
    occurredAt: timestamp(item.occurredAt, "Application lifecycle occurredAt"),
    source: requiredString(item.source, "Application lifecycle source"),
    metadata: (metadata as Record<string, unknown> | undefined) ?? {},
  };
}

function parseOutcome(value: unknown): ApplicationOutcomeEvent {
  const item = objectValue(value, "Application outcome");
  const stage = requiredString(
    item.stage,
    "Application outcome stage",
  ) as ApplicationOutcomeStage;
  if (!outcomeStages.has(stage))
    throw new Error("Application outcome stage is invalid");
  return {
    eventId: requiredString(item.eventId, "Application outcome eventId"),
    applicationId: requiredString(
      item.applicationId,
      "Application outcome applicationId",
    ),
    stage,
    occurredAt: timestamp(item.occurredAt, "Application outcome occurredAt"),
    source: requiredString(item.source, "Application outcome source"),
  };
}

export function parseNativeApplicationAnalyticsSnapshot(
  value: unknown,
): NativeApplicationAnalyticsSnapshot {
  const snapshot = objectValue(value, "Application analytics snapshot");
  if (!Array.isArray(snapshot.contexts))
    throw new Error("Analytics contexts must be an array");
  if (!Array.isArray(snapshot.lifecycleEvents)) {
    throw new Error("Analytics lifecycleEvents must be an array");
  }
  if (!Array.isArray(snapshot.outcomes))
    throw new Error("Analytics outcomes must be an array");
  return {
    contexts: snapshot.contexts.map(parseContext),
    lifecycleEvents: snapshot.lifecycleEvents.map(parseLifecycleEvent),
    outcomes: snapshot.outcomes.map(parseOutcome),
  };
}

async function sendNativeAnalytics<T>(
  message: Record<string, unknown>,
  timeoutMilliseconds = 5_000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(nativeHostName);
    const timeout = window.setTimeout(() => {
      port.disconnect();
      reject(new Error("Native application analytics request timed out"));
    }, timeoutMilliseconds);
    const finish = (): void => window.clearTimeout(timeout);
    port.onMessage.addListener((response: NativeResponse) => {
      finish();
      port.disconnect();
      if (!response.ok) {
        reject(new Error(response.error));
        return;
      }
      resolve(response.data as T);
    });
    port.onDisconnect.addListener(() => {
      const lastError = chrome.runtime.lastError;
      if (!lastError) return;
      finish();
      reject(new Error(lastError.message));
    });
    port.postMessage(message);
  });
}

async function recordCreated(
  type: string,
  payload: Record<string, unknown>,
): Promise<boolean> {
  const response = await sendNativeAnalytics<unknown>({ type, payload });
  const data = objectValue(response, `${type} response`);
  if (typeof data.created !== "boolean") {
    throw new Error(`${type} response.created must be boolean`);
  }
  return data.created;
}

export function recordNativeApplicationAnalyticsEvent(
  event: ApplicationLifecycleEvent,
): Promise<boolean> {
  return recordCreated("RECORD_APPLICATION_ANALYTICS_EVENT", {
    eventId: requiredString(event.eventId, "Analytics eventId"),
    applicationId: requiredString(
      event.applicationId,
      "Analytics applicationId",
    ),
    eventType: event.eventType,
    occurredAt: timestamp(event.occurredAt, "Analytics occurredAt"),
    source: requiredString(event.source, "Analytics source"),
    metadata: event.metadata ?? {},
  });
}

export function recordNativeApplicationAttributionContext(input: {
  eventId: string;
  context: ApplicationAttributionContext;
}): Promise<boolean> {
  return recordCreated("RECORD_APPLICATION_ATTRIBUTION_CONTEXT", {
    eventId: requiredString(input.eventId, "Attribution eventId"),
    applicationId: requiredString(
      input.context.applicationId,
      "Attribution applicationId",
    ),
    capturedAt: timestamp(input.context.capturedAt, "Attribution capturedAt"),
    jobSource: input.context.jobSource ?? null,
    atsFamily: input.context.atsFamily ?? null,
    resumeId: input.context.resumeId ?? null,
  });
}

export function recordNativeApplicationOutcome(
  outcome: ApplicationOutcomeEvent,
): Promise<boolean> {
  return recordCreated("RECORD_APPLICATION_OUTCOME", {
    eventId: requiredString(outcome.eventId, "Outcome eventId"),
    applicationId: requiredString(
      outcome.applicationId,
      "Outcome applicationId",
    ),
    stage: outcome.stage,
    occurredAt: timestamp(outcome.occurredAt, "Outcome occurredAt"),
    source: requiredString(outcome.source, "Outcome source"),
  });
}

export async function getNativeApplicationAnalyticsSnapshot(): Promise<NativeApplicationAnalyticsSnapshot> {
  return parseNativeApplicationAnalyticsSnapshot(
    await sendNativeAnalytics<unknown>({
      type: "GET_APPLICATION_ANALYTICS_SNAPSHOT",
    }),
  );
}

export async function getNativeApplicationAnalyticsSummary(
  minimumSampleForRates = 5,
): Promise<ApplicationFunnelSummary> {
  const snapshot = await getNativeApplicationAnalyticsSnapshot();
  return summarizeApplicationAnalytics({ ...snapshot, minimumSampleForRates });
}
