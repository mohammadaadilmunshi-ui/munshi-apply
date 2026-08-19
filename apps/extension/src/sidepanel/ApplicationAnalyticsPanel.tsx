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
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function friendlyBucketKey(
  kind: "source" | "ats" | "resume",
  value: string,
): string {
  if (!value || value === "UNKNOWN") {
    return kind === "source" ? "Not captured yet" : "Unknown";
  }
  if (kind === "ats") return value.replaceAll("_", " ");
  if (kind === "resume" && value.startsWith("resume-")) {
    const short = value.slice(-8);
    return `Selected résumé · …${short}`;
  }
  return value;
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
        const label =
          outcomeLabels.find(([value]) => value === stage)?.[1] ?? stage;
        setMessage(`${label} saved to this application's history.`);
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
      <section
        className="subpanel analytics-panel"
        aria-labelledby="analytics-heading"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Application history</p>
            <h3 id="analytics-heading">Analytics</h3>
          </div>
        </div>
        <div className="inline-note warning">
          Connect the MUNSHI native companion to save application history and
          outcomes on this Mac.
        </div>
      </section>
    );
  }

  const topSource = summary?.byJobSource[0] ?? null;
  const topAts = summary?.byAtsFamily[0] ?? null;
  const topResume = summary?.byResume[0] ?? null;
  const attribution = [
    topSource
      ? { kind: "source" as const, label: "Job source", bucket: topSource }
      : null,
    topAts ? { kind: "ats" as const, label: "ATS", bucket: topAts } : null,
    topResume
      ? { kind: "resume" as const, label: "Résumé", bucket: topResume }
      : null,
  ].filter((item): item is NonNullable<typeof item> => item !== null);

  return (
    <section
      className="subpanel analytics-panel"
      aria-labelledby="analytics-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Application history</p>
          <h3 id="analytics-heading">Analytics</h3>
          <p className="panel-subtitle">
            What you have actually prepared, submitted, and heard back from.
          </p>
        </div>
        <span className="badge">
          {summary ? `${summary.applicationCount} tracked` : "Loading"}
        </span>
      </div>

      {summary && (
        <div className="panel-card analytics-funnel">
          <div className="panel-title-row">
            <div>
              <span className="panel-subtitle">Your application funnel</span>
              <h3>
                {summary.applicationCount} application
                {summary.applicationCount === 1 ? "" : "s"}
              </h3>
            </div>
          </div>

          <div className="stat-grid">
            <div className="stat-tile">
              <strong>{summary.preparedCount}</strong>
              <span>Prepared</span>
            </div>
            <div className="stat-tile">
              <strong>{summary.appliedCount}</strong>
              <span>Applied</span>
            </div>
            <div className="stat-tile">
              <strong>{summary.responseCount}</strong>
              <span>Responses</span>
            </div>
            <div className="stat-tile">
              <strong>{summary.interviewCount}</strong>
              <span>Interviews</span>
            </div>
            <div className="stat-tile">
              <strong>{summary.offerCount}</strong>
              <span>Offers</span>
            </div>
            <div className="stat-tile">
              <strong>{summary.autopilotCompletedCount}</strong>
              <span>AutoPilot done</span>
            </div>
          </div>

          {summary.autopilotFailedCount > 0 && (
            <div className="inline-note warning">
              AutoPilot has {summary.autopilotFailedCount} recorded failed run
              {summary.autopilotFailedCount === 1 ? "" : "s"}. These remain in
              history so recovery patterns can be improved.
            </div>
          )}
        </div>
      )}

      {attribution.length > 0 && (
        <details className="compact-details">
          <summary>Where applications are coming from</summary>
          <div className="compact-details-body">
            <div className="attribution-list">
              {attribution.map(({ kind, label, bucket }) => (
                <div className="attribution-row" key={`${kind}-${bucket.key}`}>
                  <div>
                    <strong>
                      {label}: {friendlyBucketKey(kind, bucket.key)}
                    </strong>
                    <span>
                      {bucket.sampleCount} application
                      {bucket.sampleCount === 1 ? "" : "s"}
                    </span>
                  </div>
                  <div>
                    <strong>{formatRate(bucket.responseRate)}</strong>
                    <span>response rate</span>
                  </div>
                </div>
              ))}
            </div>
            {summary && <span>{summary.statisticalNote}</span>}
          </div>
        </details>
      )}

      <div className="panel-card soft">
        <div className="panel-title-row">
          <div>
            <span className="panel-subtitle">Keep history accurate</span>
            <h3>Update application outcome</h3>
          </div>
        </div>
        <p>
          Choose an outcome only when it actually happens. MUNSHI never guesses
          that you applied, interviewed, were rejected, or received an offer.
        </p>
        <div className="outcome-buttons">
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
        {message && (
          <div
            className={
              message.startsWith("Could not")
                ? "inline-note danger"
                : "inline-note success"
            }
          >
            {message}
          </div>
        )}
      </div>

      <details className="compact-details">
        <summary>About these analytics</summary>
        <div className="compact-details-body">
          <span>
            MUNSHI shows counts immediately but waits for enough applications
            before showing rates, so one or two applications do not create
            misleading conclusions.
          </span>
          <span>
            Attribution is descriptive. It does not prove that a job source,
            ATS, résumé, or strategy caused an outcome.
          </span>
        </div>
      </details>
    </section>
  );
}
