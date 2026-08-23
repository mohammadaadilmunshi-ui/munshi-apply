import type { ApplicationOutcomeEvent } from "./analytics";

export type ApplicationLifecycleEventType =
  | "DETECTED"
  | "PREPARED"
  | "AUTOPILOT_STARTED"
  | "AUTOPILOT_COMPLETED"
  | "AUTOPILOT_PAUSED"
  | "AUTOPILOT_FAILED"
  | "DRAFT_USED"
  | "RESUME_USED"
  | "RECRUITER_RESPONSE"
  | "JOB_SIGNALS_ANALYZED";

export type ApplicationLifecycleEvent = {
  eventId: string;
  applicationId: string;
  eventType: ApplicationLifecycleEventType;
  occurredAt: string;
  source: string;
  metadata?: Readonly<Record<string, unknown>>;
};

export type ApplicationAttributionContext = {
  applicationId: string;
  capturedAt: string;
  jobSource?: string | null;
  atsFamily?: string | null;
  resumeId?: string | null;
};

export type AttributionBucketSummary = {
  key: string;
  sampleCount: number;
  appliedCount: number;
  responseCount: number;
  interviewCount: number;
  offerCount: number;
  responseRate: number | null;
  interviewRate: number | null;
  offerRate: number | null;
  rateReason: string;
};

export type ApplicationFunnelSummary = {
  applicationCount: number;
  preparedCount: number;
  appliedCount: number;
  responseCount: number;
  assessmentCount: number;
  interviewCount: number;
  offerCount: number;
  rejectedCount: number;
  withdrawnCount: number;
  autopilotCompletedCount: number;
  autopilotFailedCount: number;
  byJobSource: readonly AttributionBucketSummary[];
  byAtsFamily: readonly AttributionBucketSummary[];
  byResume: readonly AttributionBucketSummary[];
  minimumSampleForRates: number;
  statisticalNote: string;
};

type ApplicationState = {
  applicationId: string;
  context: ApplicationAttributionContext | null;
  lifecycle: Set<ApplicationLifecycleEventType>;
  outcomes: Set<ApplicationOutcomeEvent["stage"]>;
};

function latestContexts(
  contexts: readonly ApplicationAttributionContext[],
): Map<string, ApplicationAttributionContext> {
  const latest = new Map<string, ApplicationAttributionContext>();
  for (const context of contexts) {
    if (!context.applicationId.trim()) continue;
    const existing = latest.get(context.applicationId);
    if (!existing || context.capturedAt >= existing.capturedAt) {
      latest.set(context.applicationId, context);
    }
  }
  return latest;
}

function normalizedBucket(value: string | null | undefined): string {
  const normalized = value?.trim();
  return normalized || "UNKNOWN";
}

function rate(
  count: number,
  sample: number,
  minimumSample: number,
): number | null {
  if (sample < minimumSample || sample === 0) return null;
  return Number((count / sample).toFixed(6));
}

function summarizeBuckets(
  applications: readonly ApplicationState[],
  key: (application: ApplicationState) => string,
  minimumSample: number,
): AttributionBucketSummary[] {
  const groups = new Map<string, ApplicationState[]>();
  for (const application of applications) {
    const bucket = key(application);
    groups.set(bucket, [...(groups.get(bucket) ?? []), application]);
  }
  return [...groups.entries()]
    .map(([bucket, items]) => {
      const sampleCount = items.length;
      const appliedCount = items.filter((item) =>
        item.outcomes.has("APPLIED"),
      ).length;
      const responseCount = items.filter(
        (item) =>
          item.lifecycle.has("RECRUITER_RESPONSE") ||
          item.outcomes.has("ASSESSMENT") ||
          item.outcomes.has("INTERVIEW") ||
          item.outcomes.has("OFFER"),
      ).length;
      const interviewCount = items.filter((item) =>
        item.outcomes.has("INTERVIEW"),
      ).length;
      const offerCount = items.filter((item) =>
        item.outcomes.has("OFFER"),
      ).length;
      const ratesVisible = sampleCount >= minimumSample;
      return {
        key: bucket,
        sampleCount,
        appliedCount,
        responseCount,
        interviewCount,
        offerCount,
        responseRate: rate(responseCount, sampleCount, minimumSample),
        interviewRate: rate(interviewCount, sampleCount, minimumSample),
        offerRate: rate(offerCount, sampleCount, minimumSample),
        rateReason: ratesVisible
          ? "Minimum sample gate satisfied; rates are descriptive and do not establish causality."
          : `Rates withheld until this bucket has at least ${minimumSample} applications.`,
      } satisfies AttributionBucketSummary;
    })
    .sort(
      (left, right) =>
        right.sampleCount - left.sampleCount ||
        left.key.localeCompare(right.key),
    );
}

export function summarizeApplicationAnalytics(input: {
  contexts: readonly ApplicationAttributionContext[];
  lifecycleEvents: readonly ApplicationLifecycleEvent[];
  outcomes: readonly ApplicationOutcomeEvent[];
  minimumSampleForRates?: number;
}): ApplicationFunnelSummary {
  const minimumSample = input.minimumSampleForRates ?? 5;
  if (!Number.isSafeInteger(minimumSample) || minimumSample < 1) {
    throw new Error("minimumSampleForRates must be a positive integer");
  }

  const contexts = latestContexts(input.contexts);
  const applications = new Map<string, ApplicationState>();
  const ensure = (applicationId: string): ApplicationState => {
    const normalized = applicationId.trim();
    if (!normalized) throw new Error("Analytics events require applicationId");
    const existing = applications.get(normalized);
    if (existing) return existing;
    const created: ApplicationState = {
      applicationId: normalized,
      context: contexts.get(normalized) ?? null,
      lifecycle: new Set(),
      outcomes: new Set(),
    };
    applications.set(normalized, created);
    return created;
  };

  for (const context of contexts.values())
    ensure(context.applicationId).context = context;
  for (const event of input.lifecycleEvents)
    ensure(event.applicationId).lifecycle.add(event.eventType);
  for (const outcome of input.outcomes)
    ensure(outcome.applicationId).outcomes.add(outcome.stage);

  const items = [...applications.values()];
  const hasResponse = (item: ApplicationState): boolean =>
    item.lifecycle.has("RECRUITER_RESPONSE") ||
    item.outcomes.has("ASSESSMENT") ||
    item.outcomes.has("INTERVIEW") ||
    item.outcomes.has("OFFER");

  return {
    applicationCount: items.length,
    preparedCount: items.filter(
      (item) =>
        item.lifecycle.has("PREPARED") ||
        item.lifecycle.has("AUTOPILOT_STARTED") ||
        item.lifecycle.has("AUTOPILOT_COMPLETED"),
    ).length,
    appliedCount: items.filter((item) => item.outcomes.has("APPLIED")).length,
    responseCount: items.filter(hasResponse).length,
    assessmentCount: items.filter((item) => item.outcomes.has("ASSESSMENT"))
      .length,
    interviewCount: items.filter((item) => item.outcomes.has("INTERVIEW"))
      .length,
    offerCount: items.filter((item) => item.outcomes.has("OFFER")).length,
    rejectedCount: items.filter((item) => item.outcomes.has("REJECTED")).length,
    withdrawnCount: items.filter((item) => item.outcomes.has("WITHDRAWN"))
      .length,
    autopilotCompletedCount: items.filter((item) =>
      item.lifecycle.has("AUTOPILOT_COMPLETED"),
    ).length,
    autopilotFailedCount: items.filter((item) =>
      item.lifecycle.has("AUTOPILOT_FAILED"),
    ).length,
    byJobSource: summarizeBuckets(
      items,
      (item) => normalizedBucket(item.context?.jobSource),
      minimumSample,
    ),
    byAtsFamily: summarizeBuckets(
      items,
      (item) => normalizedBucket(item.context?.atsFamily),
      minimumSample,
    ),
    byResume: summarizeBuckets(
      items,
      (item) => normalizedBucket(item.context?.resumeId),
      minimumSample,
    ),
    minimumSampleForRates: minimumSample,
    statisticalNote:
      "Counts describe observed application history. Rates are withheld below the configured sample gate and remain descriptive; they do not prove that a source, ATS, résumé, or strategy caused an outcome.",
  };
}
