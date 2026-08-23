import { useEffect, useMemo, useState } from "react";
import {
  analyzeJobSignals,
  buildPageJobSignalSource,
  type JobSignalReport,
  type OpportunityPreflightState,
} from "@munshi-apply/application-model";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  getLatestNativeJobSignalReport,
  saveNativeJobSignalReport,
  type PersistedJobSignalReport,
} from "../messaging/native-job-signals";
import { buildJobSignalView } from "./job-signal-view";

const disclaimer =
  "Job signals describe evidence found in the supplied job/application context. They do not diagnose employer culture, toxicity, intent, or future workplace conditions.";

function stableId(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function restoredReport(report: PersistedJobSignalReport): JobSignalReport {
  return {
    overallSignal: report.overallSignal,
    overallScore: report.overallScore,
    dimensions: report.dimensions,
    signals: report.signals,
    disclaimer,
  };
}

function friendlyEvidence(value: string): string {
  return value
    .replaceAll("_", " ")
    .replaceAll("=true", ": yes")
    .replaceAll("=false", ": no")
    .replaceAll("=", ": ")
    .replaceAll(";", " · ");
}

function priorityLabel(value: string): string {
  switch (value) {
    case "PRIORITIZE":
      return "Strong priority";
    case "CONSIDER":
      return "Worth considering";
    case "REVIEW":
      return "Review before applying";
    case "HOLD":
      return "Hold for review";
    case "INSUFFICIENT_DATA":
      return "Need more evidence";
    default:
      return value.replaceAll("_", " ");
  }
}

export function JobSignalPanel({
  page,
  applicationId,
  nativeAvailable,
  preflightState,
  accountRequired,
  manualRequiredControls,
}: {
  page: ApplicationPage;
  applicationId: string;
  nativeAvailable: boolean;
  preflightState: OpportunityPreflightState;
  accountRequired: boolean;
  manualRequiredControls: number;
}) {
  const [persisted, setPersisted] = useState<PersistedJobSignalReport | null>(
    null,
  );
  const [message, setMessage] = useState("");
  const source = useMemo(
    () =>
      buildPageJobSignalSource(page, {
        applicationId,
        accountRequired,
        manualRequiredControls,
      }),
    [accountRequired, applicationId, manualRequiredControls, page],
  );
  const liveReport = useMemo(() => analyzeJobSignals(source.input), [source]);

  useEffect(() => {
    let cancelled = false;
    if (!nativeAvailable || !applicationId.trim()) {
      setPersisted(null);
      setMessage(
        nativeAvailable
          ? "MUNSHI will save job signals once this application has a durable record."
          : "Job signals are available for this page, but history requires the native companion.",
      );
      return () => {
        cancelled = true;
      };
    }

    void (async () => {
      setMessage("");
      let latest = await getLatestNativeJobSignalReport({
        applicationId,
        jobId: source.jobId,
        sourceIdentity:
          page.applicationState === "JOB_CONTEXT"
            ? source.sourceIdentity
            : undefined,
      });
      const shouldPersistJobContext =
        page.applicationState === "JOB_CONTEXT" &&
        source.input.description !== null &&
        latest?.sourceFingerprint !== source.sourceFingerprint;
      if (shouldPersistJobContext) {
        latest = await saveNativeJobSignalReport({
          reportId: `job-signal-${stableId(`${applicationId}|${source.sourceFingerprint}`)}`,
          applicationId,
          jobId: source.jobId,
          sourceIdentity: source.sourceIdentity,
          sourceFingerprint: source.sourceFingerprint,
          evaluatedAt: page.observedAt,
          report: liveReport,
        });
      }
      if (cancelled) return;
      setPersisted(latest);
      if (shouldPersistJobContext) {
        setMessage("Posting signals saved with this application.");
      } else if (latest) {
        setMessage(
          "Using the latest saved posting signals for this application.",
        );
      }
    })().catch((error: unknown) => {
      if (cancelled) return;
      setMessage(
        error instanceof Error
          ? `Saved job-signal history is unavailable: ${error.message}`
          : "Saved job-signal history is temporarily unavailable.",
      );
    });

    return () => {
      cancelled = true;
    };
  }, [
    applicationId,
    liveReport,
    nativeAvailable,
    page.applicationState,
    page.observedAt,
    source.input.description,
    source.jobId,
    source.sourceIdentity,
    source.sourceFingerprint,
  ]);

  const report =
    page.applicationState === "JOB_CONTEXT" || !persisted
      ? liveReport
      : restoredReport(persisted);
  const view = useMemo(
    () => buildJobSignalView({ report, preflightState }),
    [preflightState, report],
  );
  const knownRows = view.rows.filter((row) => row.score !== null);
  const liveFriction = liveReport.dimensions.APPLICATION_FRICTION;
  const atFinalOwnerBoundary = Boolean(page.finalSubmissionBoundary);
  const displayedPriority =
    atFinalOwnerBoundary && view.opportunity.priority === "HOLD"
      ? "Final owner review"
      : priorityLabel(view.opportunity.priority);
  const displayedExplanation =
    atFinalOwnerBoundary && view.opportunity.priority === "HOLD"
      ? "MUNSHI detected the final submit step. Submission is always left to you; reaching this boundary is not itself a negative signal about the job. Review any separate eligibility findings above before submitting."
      : view.opportunity.explanation;

  return (
    <section
      className="subpanel job-signal-panel"
      aria-labelledby="job-signal-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Opportunity snapshot</p>
          <h3 id="job-signal-heading">Job Signals</h3>
          <p className="panel-subtitle">
            Evidence MUNSHI found in the posting and application flow.
          </p>
        </div>
        <span
          className={report.overallSignal === "HIGH" ? "badge review" : "badge"}
        >
          {view.overallLabel}
          {view.overallScore === null ? "" : ` · ${view.overallScore}/100`}
        </span>
      </div>

      <div className="panel-card signal-overview">
        <div className="panel-title-row">
          <div>
            <span className="panel-subtitle">Opportunity status</span>
            <h3>{displayedPriority}</h3>
          </div>
          {view.opportunity.priorityScore !== null && !atFinalOwnerBoundary && (
            <span className="badge">{view.opportunity.priorityScore}/100</span>
          )}
        </div>
        <p>{displayedExplanation}</p>

        <div className="stat-grid">
          <div className="stat-tile">
            <strong>{view.knownDimensionCount}</strong>
            <span>Known signals</span>
          </div>
          <div className="stat-tile">
            <strong>{view.unknownDimensionCount}</strong>
            <span>Still unknown</span>
          </div>
          <div className="stat-tile">
            <strong>
              {liveFriction.score === null ? "—" : `${liveFriction.score}`}
            </strong>
            <span>Form friction</span>
          </div>
        </div>

        {atFinalOwnerBoundary && (
          <div className="inline-note success">
            Final submission is an owner-control boundary. It does not count as
            evidence that the employer or opportunity is poor.
          </div>
        )}

        {persisted && page.applicationState !== "JOB_CONTEXT" && (
          <div className="inline-note">
            Showing the saved job-posting report while keeping current form
            friction separate, so application-page changes do not overwrite the
            original posting evidence.
          </div>
        )}
        {message && <div className="inline-note">{message}</div>}
      </div>

      {knownRows.length ? (
        <details className="compact-details">
          <summary>
            View {knownRows.length} evidence-backed signal
            {knownRows.length === 1 ? "" : "s"}
          </summary>
          <div className="compact-details-body">
            {knownRows.map((row) => (
              <div className="signal-row" key={row.dimension}>
                <div className="signal-row-heading">
                  <strong>{row.label}</strong>
                  <span
                    className={
                      row.disposition === "CONCERN" ? "badge review" : "badge"
                    }
                  >
                    {row.score}/100
                  </span>
                </div>
                <p>
                  {row.directionLabel} · confidence{" "}
                  {Math.round(row.confidence * 100)}%
                </p>
                <p>
                  Source:{" "}
                  {[...new Set(row.evidenceSources)]
                    .map((source) =>
                      source === "APPLICATION_OBSERVATION"
                        ? "observed application flow"
                        : "job posting",
                    )
                    .join(", ")}
                </p>
                {row.explanations.slice(0, 2).map((explanation, index) => (
                  <p key={`${row.dimension}-explanation-${index}`}>
                    {explanation}
                  </p>
                ))}
                {row.evidence.length > 0 && (
                  <div className="inline-note">
                    Exact evidence:{" "}
                    {row.evidence.map(friendlyEvidence).join(" · ")}
                  </div>
                )}
              </div>
            ))}
          </div>
        </details>
      ) : (
        <div className="inline-note warning">
          Not enough posting evidence yet. MUNSHI will leave missing dimensions
          unknown rather than inventing employer conditions or candidate fit.
        </div>
      )}

      {view.opportunity.riskFactors.length > 0 && !atFinalOwnerBoundary && (
        <details className="compact-details">
          <summary>Review factors</summary>
          <div className="compact-details-body">
            {view.opportunity.riskFactors.map((factor) => (
              <div className="inline-note danger" key={factor}>
                {factor}
              </div>
            ))}
          </div>
        </details>
      )}

      <details className="compact-details signal-methodology">
        <summary>How to read Job Signals</summary>
        <div className="compact-details-body">
          <span>{report.disclaimer}</span>
          <span>
            Scores summarize available evidence only. Unknown information stays
            unknown, and Job Signals never override confirmed eligibility facts.
          </span>
        </div>
      </details>
    </section>
  );
}
