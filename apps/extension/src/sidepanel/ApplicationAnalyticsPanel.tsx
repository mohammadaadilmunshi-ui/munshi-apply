import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApplicationPage } from "@munshi-apply/contracts";
import type {
  ApplicationFunnelSummary,
  ApplicationLifecycleEventType,
  ApplicationOutcomeStage,
} from "@munshi-apply/application-model";
import type { AutoPilotControllerStatus } from "../messaging/client";
import {
  getNativeApplicationAnalyticsSummary,
  recordNativeApplicationAnalyticsEvent,
  recordNativeApplicationAttributionContext,
  recordNativeApplicationOutcome,
} from "../messaging/native-application-analytics";

function hash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function timezoneAware(value: string): string {
  return /(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
    ? value
    : new Date(value).toISOString();
}

function detectedJobSource(url: string): string | null {
  try {
    const parsed = new URL(url);
    for (const key of ["utm_source", "source", "jobSource", "job_source"]) {
      const value = parsed.searchParams.get(key)?.trim();
      if (value && value.length <= 120) return value;
    }
  } catch {
    return null;
  }
  return null;
}

function lifecycleType(
  status: AutoPilotControllerStatus | null,
): ApplicationLifecycleEventType | null {
  if (!status) return null;
  switch (status.session.status) {
    case "RUNNING":
    case "WAITING_RESCAN":
    case "WAITING_NAVIGATION":
      return "AUTOPILOT_STARTED";
    case "PAUSED_ERROR":
      return "AUTOPILOT_FAILED";
    case "PAUSED_OWNER":
    case "PAUSED_REVIEW":
    case "PAUSED_SECURITY":
    case "PAUSED_FINAL":
      return "AUTOPILOT_PAUSED";
    case "IDLE":
    case "STOPPED":
      return null;
  }
}

function formatRate(value: number | null): string {
  return value === null ? "withheld" : `${Math.round(value * 100)}%`;
}

const outcomeLabels: readonly [ApplicationOutcomeStage, string][] = [
  ["APPLIED", "Applied"],
  ["ASSESSMENT", "Assessment"],
  ["INTERVIEW", "Interview"],
  ["OFFER", "Offer"],
  ["REJECTED", "Rejected"],
  ["WITHDRAWN", "Withdrawn"],
];

export function ApplicationAnalyticsPanel({
  page,
  applicationId,
  selectedResumeId,
  nativeAvailable,
  autoPilotStatus,
}: {
  page: ApplicationPage;
  applicationId: string;
  selectedResumeId: string | null;
  nativeAvailable: boolean;
  autoPilotStatus: AutoPilotControllerStatus | null;
}) {
  const [summary, setSummary] = useState<ApplicationFunnelSummary | null>(null);
  const [message, setMessage] = useState("");
  const [busyOutcome, setBusyOutcome] =
    useState<ApplicationOutcomeStage | null>(null);
  const source = useMemo(() => detectedJobSource(page.url), [page.url]);

  const refresh = useCallback(async () => {
    if (!nativeAvailable) {
      setSummary(null);
      return;
    }
    setSummary(await getNativeApplicationAnalyticsSummary(5));
  }, [nativeAvailable]);

  useEffect(() => {
    if (!nativeAvailable || !applicationId.trim()) return;
    let cancelled = false;
    const observedAt = timezoneAware(page.observedAt);
    const pageKey = [
      applicationId,
      page.pageId,
      page.pageFingerprint,
      observedAt,
    ].join("|");

    void (async () => {
      await recordNativeApplicationAttributionContext({
        eventId: `attribution-${hash(`${pageKey}|${selectedResumeId ?? "none"}`)}`,
        context: {
          applicationId,
          capturedAt: observedAt,
          jobSource: source,
          atsFamily: page.atsFamily ?? null,
          resumeId: selectedResumeId,
        },
      });
      await recordNativeApplicationAnalyticsEvent({
        eventId: `analytics-${hash(`${pageKey}|DETECTED`)}`,
        applicationId,
        eventType: "DETECTED",
        occurredAt: observedAt,
        source: "extension",
        metadata: { applicationState: page.applicationState },
      });
      await recordNativeApplicationAnalyticsEvent({
        eventId: `analytics-${hash(`${pageKey}|PREPARED`)}`,
        applicationId,
        eventType: "PREPARED",
        occurredAt: observedAt,
        source: "extension",
        metadata: {},
      });
      if (!cancelled) await refresh();
    })().catch((error: unknown) => {
      if (!cancelled) {
        setMessage(
          error instanceof Error
            ? `Analytics capture unavailable: ${error.message}`
            : "Analytics capture is temporarily unavailable.",
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [
    applicationId,
    nativeAvailable,
    page.applicationState,
    page.atsFamily,
    page.observedAt,
    page.pageFingerprint,
    page.pageId,
    refresh,
    selectedResumeId,
    source,
  ]);

  useEffect(() => {
    if (!nativeAvailable || !applicationId.trim() || !autoPilotStatus) return;
    const eventType = lifecycleType(autoPilotStatus);
    if (!eventType) return;
    const at = timezoneAware(autoPilotStatus.session.updatedAt);
    const identity = [
      applicationId,
      autoPilotStatus.session.sessionId,
      eventType,
      autoPilotStatus.session.status,
      at,
    ].join("|");
    void recordNativeApplicationAnalyticsEvent({
      eventId: `analytics-${hash(identity)}`,
      applicationId,
      eventType,
      occurredAt: at,
      source: "extension",
      metadata: {},
    })
      .then(() => refresh())
      .catch((error: unknown) => {
        setMessage(
          error instanceof Error
            ? `AutoPilot analytics unavailable: ${error.message}`
            : "AutoPilot analytics are temporarily unavailable.",
        );
      });
  }, [applicationId, autoPilotStatus, nativeAvailable, refresh]);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(
        error instanceof Error
          ? `Analytics history unavailable: ${error.message}`
          : "Analytics history is temporarily unavailable.",
      );
    });
  }, [refresh]);

  const recordOutcome = useCallback(
    async (stage: ApplicationOutcomeStage) => {
      if (!applicationId.trim() || !nativeAvailable) return;
      setBusyOutcome(stage);
      setMessage("");
      try {
        const occurredAt = new Date().toISOString();
        await recordNativeApplicationOutcome({
          eventId: `outcome-${hash(`${applicationId}|${stage}|${occurredAt}`)}`,
          applicationId,
          stage,
          occurredAt,
          source: "owner",
        });
        setMessage(`${stage.toLocaleLowerCase("en-US")} outcome recorded.`);
        await refresh();
      } catch (error) {
        setMessage(
          error instanceof Error
            ? `Could not record outcome: ${error.message}`
            : "Could not record outcome.",
        );
      } finally {
        setBusyOutcome(null);
      }
    },
    [applicationId, nativeAvailable, refresh],
  );

  if (!nativeAvailable) {
    return (
      <section className="answer-list" aria-labelledby="analytics-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Observed application history</p>
            <h3 id="analytics-heading">Analytics & attribution</h3>
          </div>
        </div>
        <div className="safety-callout">
          <strong>Durable analytics unavailable</strong>
          <span>
            The current native companion must be available before MUNSHI stores
            attribution or application outcomes.
          </span>
        </div>
      </section>
    );
  }

  const topSource = summary?.byJobSource[0] ?? null;
  const topAts = summary?.byAtsFamily[0] ?? null;
  const topResume = summary?.byResume[0] ?? null;

  return (
    <section className="answer-list" aria-labelledby="analytics-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Observed application history</p>
          <h3 id="analytics-heading">Analytics & attribution</h3>
        </div>
        <span className="badge">
          {summary ? `${summary.applicationCount} applications` : "Loading"}
        </span>
      </div>

      {summary && (
        <>
          <div className="cloud-connection">
            <strong>
              Funnel · {summary.preparedCount} prepared · {summary.appliedCount}{" "}
              applied · {summary.responseCount} responses ·{" "}
              {summary.interviewCount} interviews · {summary.offerCount} offers
            </strong>
            <span>
              AutoPilot: {summary.autopilotCompletedCount} completed ·{" "}
              {summary.autopilotFailedCount} failed
            </span>
            <span>{summary.statisticalNote}</span>
          </div>

          {[topSource, topAts, topResume].map((bucket, index) =>
            bucket ? (
              <article className="answer-card" key={`${bucket.key}-${index}`}>
                <strong>
                  {index === 0 ? "Job source" : index === 1 ? "ATS" : "Résumé"}:{" "}
                  {bucket.key}
                </strong>
                <span>
                  {bucket.sampleCount} applications · response{" "}
                  {formatRate(bucket.responseRate)} · interview{" "}
                  {formatRate(bucket.interviewRate)} · offer{" "}
                  {formatRate(bucket.offerRate)}
                </span>
                <span>{bucket.rateReason}</span>
              </article>
            ) : null,
          )}
        </>
      )}

      <div className="cloud-connection">
        <strong>Record an actual outcome</strong>
        <span>
          These are owner-confirmed events. MUNSHI does not infer an application
          was submitted, rejected, interviewed, or offered from page appearance.
        </span>
        <div className="button-row">
          {outcomeLabels.map(([stage, label]) => (
            <button
              key={stage}
              type="button"
              className="secondary-button"
              disabled={busyOutcome !== null}
              onClick={() => void recordOutcome(stage)}
            >
              {busyOutcome === stage ? "Saving…" : label}
            </button>
          ))}
        </div>
      </div>
      {message && <span className="url">{message}</span>}
    </section>
  );
}
