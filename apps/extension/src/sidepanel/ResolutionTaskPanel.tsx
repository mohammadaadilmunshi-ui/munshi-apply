import { useEffect, useMemo, useState } from "react";
import type {
  ResolutionTask,
  ResolutionTaskStatus,
} from "@munshi-apply/application-model";
import { listNativeResolutionTasks } from "../messaging/native-resolution";
import {
  buildResolutionTaskQueueView,
  type ResolutionTaskQueueView,
} from "./resolution-task-view";

const activeStatuses: readonly ResolutionTaskStatus[] = [
  "PENDING",
  "RESOLVING",
  "WAITING_FOR_USER",
];

function mergeTasks(groups: readonly ResolutionTask[][]): ResolutionTask[] {
  const byId = new Map<string, ResolutionTask>();
  for (const group of groups) {
    for (const task of group) {
      const existing = byId.get(task.taskId);
      if (!existing || Date.parse(task.updatedAt) > Date.parse(existing.updatedAt)) {
        byId.set(task.taskId, task);
      }
    }
  }
  return [...byId.values()];
}

function dispositionNote(
  disposition: ResolutionTaskQueueView["rows"][number]["disposition"],
): string {
  switch (disposition) {
    case "OWNER_REQUIRED":
      return "MUNSHI will not continue through this decision without the required owner action.";
    case "GUARDED_RESOLUTION":
      return "Policy permits an evidence-backed resolver path, with verification still required before AutoPilot continues.";
    case "REVIEW":
      return "This task stays paused for review because no safe automatic path is currently permitted.";
  }
}

export function ResolutionTaskQueueBody({
  view,
  loading,
  message,
  nativeAvailable,
}: {
  view: ResolutionTaskQueueView;
  loading: boolean;
  message: string;
  nativeAvailable: boolean;
}) {
  if (!nativeAvailable) {
    return (
      <div className="inline-note warning">
        Resolution Task history requires the native companion so task state and
        resume checkpoints remain durable.
      </div>
    );
  }

  if (loading) {
    return <div className="inline-note">Loading durable Resolution Tasks…</div>;
  }

  return (
    <>
      {message && <div className="inline-note warning">{message}</div>}

      <div className="metrics">
        <article>
          <strong>{view.currentOpenCount}</strong>
          <span>open now</span>
        </article>
        <article>
          <strong>{view.ownerRequiredCount}</strong>
          <span>need you</span>
        </article>
        <article>
          <strong>{view.guardedResolutionCount}</strong>
          <span>guarded candidates</span>
        </article>
      </div>

      {view.rows.length ? (
        <div className="answer-list">
          {view.rows.map((row) => (
            <article className="answer-card" key={row.taskId}>
              <div className="answer-heading">
                <div>
                  <strong>{row.title}</strong>
                  <span>
                    {row.categoryLabel} · {row.statusLabel} ·{" "}
                    {row.riskLevel.toLocaleLowerCase("en-US")} risk
                  </span>
                </div>
                <span
                  className={
                    row.disposition === "OWNER_REQUIRED"
                      ? "badge review"
                      : "badge"
                  }
                >
                  {row.disposition === "OWNER_REQUIRED" ? "Needs you" : "Tracked"}
                </span>
              </div>
              <span>{row.reason}</span>
              <div
                className={
                  row.disposition === "OWNER_REQUIRED"
                    ? "inline-note warning"
                    : "inline-note"
                }
              >
                <strong>{row.dispositionLabel}.</strong>{" "}
                {dispositionNote(row.disposition)}
              </div>
              {row.reusableApplicationCount > 1 && (
                <div className="inline-note success">
                  Reusable scope detected across {row.reusableApplicationCount}{" "}
                  applications. A single confirmed source-of-truth update may
                  clear the matching work in each application after revalidation.
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="panel-card soft">
          <strong>No unresolved tasks for this application</strong>
          <p>
            MUNSHI has no durable Resolution Task currently blocking or waiting
            on this application.
          </p>
        </div>
      )}

      {view.otherApplicationOpenCount > 0 && (
        <div className="inline-note">
          {view.otherApplicationOpenCount} additional open task
          {view.otherApplicationOpenCount === 1 ? " is" : "s are"} tracked across
          other applications.
        </div>
      )}

      <details className="compact-details">
        <summary>Resolution safety rules</summary>
        <div className="compact-details-body">
          <span>
            High-risk facts are never guessed or resolved by grounded AI.
            Blocking conflicts and human-verification boundaries remain
            owner-controlled.
          </span>
          <span>
            “Eligible for guarded resolution” means the task policy permits a
            verified resolver path. It does not mean MUNSHI has already changed
            the underlying answer or bypassed review.
          </span>
          {view.reusableGroupCount > 0 && (
            <span>
              {view.reusableGroupCount} reusable task group
              {view.reusableGroupCount === 1 ? " is" : "s are"} shared with at
              least one other application.
            </span>
          )}
        </div>
      </details>
    </>
  );
}

export function ResolutionTaskPanel({
  applicationId,
  nativeAvailable,
  refreshRevision = 0,
}: {
  applicationId: string;
  nativeAvailable: boolean;
  refreshRevision?: number;
}) {
  const [tasks, setTasks] = useState<ResolutionTask[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [manualRefresh, setManualRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const normalizedApplicationId = applicationId.trim();
    if (!nativeAvailable || !normalizedApplicationId) {
      setTasks([]);
      setMessage("");
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    setMessage("");
    void Promise.all(
      activeStatuses.map((status) =>
        listNativeResolutionTasks({ status, limit: 500 }),
      ),
    )
      .then((groups) => {
        if (!cancelled) setTasks(mergeTasks(groups));
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setTasks([]);
        setMessage(
          error instanceof Error
            ? `Resolution Task history is unavailable: ${error.message}`
            : "Resolution Task history is temporarily unavailable.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [applicationId, manualRefresh, nativeAvailable, refreshRevision]);

  const view = useMemo(
    () => buildResolutionTaskQueueView(tasks, applicationId),
    [applicationId, tasks],
  );

  return (
    <section className="subpanel" aria-labelledby="resolution-task-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Resolution Orchestrator</p>
          <h3 id="resolution-task-heading">Resolution Queue</h3>
          <p className="panel-subtitle">
            Durable issues MUNSHI is tracking before this application can safely
            continue.
          </p>
        </div>
        <button
          className="quiet"
          type="button"
          disabled={!nativeAvailable || loading}
          onClick={() => setManualRefresh((value) => value + 1)}
        >
          Refresh
        </button>
      </div>

      <ResolutionTaskQueueBody
        view={view}
        loading={loading}
        message={message}
        nativeAvailable={nativeAvailable}
      />
    </section>
  );
}
