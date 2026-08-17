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
        accountRequired,
        manualRequiredControls,
      }),
    [accountRequired, manualRequiredControls, page],
  );
  const liveReport = useMemo(() => analyzeJobSignals(source.input), [source]);

  useEffect(() => {
    let cancelled = false;
    if (!nativeAvailable || !applicationId.trim()) {
      setPersisted(null);
      setMessage(
        nativeAvailable
          ? "Job Signal persistence will begin when this application has a durable id."
          : "Job Signals are available locally; durable history requires the native companion.",
      );
      return () => {
        cancelled = true;
      };
    }

    void (async () => {
      setMessage("");
      let latest = await getLatestNativeJobSignalReport(applicationId);
      const shouldPersistJobContext =
        page.applicationState === "JOB_CONTEXT" &&
        source.input.description !== null &&
        latest?.sourceFingerprint !== source.sourceFingerprint;
      if (shouldPersistJobContext) {
        latest = await saveNativeJobSignalReport({
          reportId: `job-signal-${stableId(`${applicationId}|${source.sourceFingerprint}`)}`,
          applicationId,
          sourceFingerprint: source.sourceFingerprint,
          evaluatedAt: page.observedAt,
          report: liveReport,
        });
      }
      if (cancelled) return;
      setPersisted(latest);
      if (shouldPersistJobContext) {
        setMessage("Job-posting signals saved to this application record.");
      } else if (latest) {
        setMessage("Showing the latest durable job-posting signal report.");
      }
    })().catch((error: unknown) => {
      if (cancelled) return;
      setMessage(
        error instanceof Error
          ? `Job Signal history unavailable: ${error.message}`
          : "Job Signal history is temporarily unavailable.",
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

  return (
    <section className="answer-list" aria-labelledby="job-signal-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Evidence-backed opportunity intelligence</p>
          <h3 id="job-signal-heading">Job Signals</h3>
        </div>
        <span
          className={
            report.overallSignal === "HIGH" ? "badge review" : "badge"
          }
        >
          {view.overallLabel}
          {view.overallScore === null ? "" : ` · ${view.overallScore}/100`}
        </span>
      </div>

      <div className="cloud-connection">
        <strong>
          Opportunity priority: {view.opportunity.priority.replaceAll("_", " ")}
          {view.opportunity.priorityScore === null
            ? ""
            : ` · ${view.opportunity.priorityScore}/100`}
        </strong>
        <span>{view.opportunity.explanation}</span>
        <span>
          {view.knownDimensionCount} dimensions have evidence ·{" "}
          {view.unknownDimensionCount} remain unknown
        </span>
        {persisted && page.applicationState !== "JOB_CONTEXT" && (
          <span>
            Posting report restored from {persisted.evaluatedAt}. Current form
            churn does not replace the posting evidence.
          </span>
        )}
        {persisted &&
          page.applicationState !== "JOB_CONTEXT" &&
          liveFriction.score !== null && (
            <span>
              Live application friction: {liveFriction.score}/100 · observed on
              the current form only
            </span>
          )}
        {message && <span>{message}</span>}
      </div>

      {knownRows.length ? (
        knownRows.map((row) => (
          <article className="answer-card" key={row.dimension}>
            <strong>
              {row.label} · {row.score}/100 · {row.disposition.toLowerCase()}
            </strong>
            <span>Confidence: {Math.round(row.confidence * 100)}%</span>
            {row.evidence.map((evidence, index) => (
              <span key={`${row.dimension}-evidence-${index}`}>
                Evidence: {evidence}
              </span>
            ))}
            {row.explanations.map((explanation, index) => (
              <span key={`${row.dimension}-explanation-${index}`}>
                {explanation}
              </span>
            ))}
          </article>
        ))
      ) : (
        <div className="safety-callout">
          <strong>Not enough job evidence yet</strong>
          <span>
            MUNSHI will keep these dimensions unknown rather than infer employer
            conditions or candidate fit from missing information.
          </span>
        </div>
      )}

      {view.opportunity.riskFactors.length > 0 && (
        <div className="cloud-connection">
          <strong>Review factors</strong>
          {view.opportunity.riskFactors.map((factor) => (
            <span className="diagnostic-error" key={factor}>
              {factor}
            </span>
          ))}
        </div>
      )}
      <span className="url">{report.disclaimer}</span>
    </section>
  );
}
