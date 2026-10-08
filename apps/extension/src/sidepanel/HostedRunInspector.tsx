import { useCallback, useEffect, useRef, useState } from "react";
import { getHostedRunStatusFromExtension } from "../messaging/client";
import type { HostedRunStatus } from "../messaging/native";
import { isHostedApplicationSelected } from "./hosted-run-identity";

const storageKey = "munshi-hosted-run-inspector-application-v1";
export function HostedRunInspector({
  nativeAvailable,
  onHostedRunFound,
}: {
  nativeAvailable: boolean;
  onHostedRunFound: (found: boolean) => void;
}) {
  const [applicationId, setApplicationId] = useState("");
  const [snapshot, setSnapshot] = useState<HostedRunStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    void chrome.storage.local
      .get(storageKey)
      .then((stored) => {
        if (typeof stored[storageKey] === "string") {
          setApplicationId(stored[storageKey] as string);
        }
      })
      .catch(() => undefined);
  }, []);

  const refresh = useCallback(async () => {
    if (
      !nativeAvailable ||
      !isHostedApplicationSelected(applicationId) ||
      inFlight.current
    )
      return;
    inFlight.current = true;
    setBusy(true);
    try {
      const current = await getHostedRunStatusFromExtension(applicationId);
      if (current.source !== "NETCUP_APPLY_DATABASE") {
        throw new Error(
          "Status was not returned by the canonical Netcup runtime.",
        );
      }
      setSnapshot(current);
      onHostedRunFound(true);
      setError("");
      await chrome.storage.local.set({ [storageKey]: applicationId });
    } catch (cause) {
      setSnapshot(null);
      // Keep a hosted identity locked against local AutoPilot even while SSH
      // is unavailable; never interpret monitor failure as permission to
      // create a second browser application.
      onHostedRunFound(true);
      setError(
        cause instanceof Error
          ? cause.message
          : "Hosted-run status unavailable.",
      );
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }, [applicationId, nativeAvailable, onHostedRunFound]);

  useEffect(() => {
    // A configured hosted application identity always blocks local AutoPilot,
    // including when native messaging/SSH is offline. Failure to observe is
    // never permission to launch a competing application.
    const selected = isHostedApplicationSelected(applicationId);
    onHostedRunFound(selected);
    if (!nativeAvailable || !selected) return;
    void refresh();
    const id = window.setInterval(() => void refresh(), 10000);
    return () => window.clearInterval(id);
  }, [applicationId, nativeAvailable, onHostedRunFound, refresh]);

  return (
    <section className="hosted-run-inspector">
      <div className="section-heading">
        <div>
          <p className="eyebrow">One application, one authoritative runtime</p>
          <h2>Netcup live application inspector</h2>
        </div>
        <span className="badge">Read-only</span>
      </div>
      <p>
        See the exact hosted Apply session and worker state used by the MUNSHI
        dashboard and terminal. This panel never starts a second AutoPilot or
        issues submission authority.
      </p>
      <label htmlFor="hosted-run-application-id">
        Existing Hunter application ID
      </label>
      <input
        id="hosted-run-application-id"
        type="text"
        value={applicationId}
        onChange={(event) => {
          setSnapshot(null);
          const next = event.target.value.trim();
          onHostedRunFound(isHostedApplicationSelected(next));
          setApplicationId(next);
        }}
        placeholder="application-..."
        autoComplete="off"
      />
      <button
        type="button"
        className="quiet"
        onClick={() => void refresh()}
        disabled={
          busy ||
          !nativeAvailable ||
          !isHostedApplicationSelected(applicationId)
        }
      >
        {busy ? "Checking Netcup…" : "Refresh hosted run"}
      </button>
      {!nativeAvailable && (
        <p className="diagnostic-error">
          The installed native companion is unavailable or outdated. No hosted
          run evidence can be displayed.
        </p>
      )}
      {error && <p className="diagnostic-error">{error}</p>}
      {snapshot?.state === "NOT_FOUND" && (
        <p>
          No matching application exists in the configured hosted Apply
          database.
        </p>
      )}
      {snapshot?.state === "AMBIGUOUS" && (
        <p className="diagnostic-error">
          Multiple sessions detected. Resolve the duplicate state before
          operating.
        </p>
      )}
      {snapshot?.state === "FOUND" && (
        <div className="cloud-connection">
          <strong>
            Current hosted state: {snapshot.session?.state ?? "UNKNOWN"}
          </strong>
          <span>Source: Netcup production Apply (read-only SQLite)</span>
          <span>Session: {snapshot.session?.session_id ?? "Unknown"}</span>
          <span>Plan: {snapshot.session?.plan_id ?? "Unknown"}</span>
          <span>
            Checkpoint: {snapshot.session?.checkpoint_id ?? "None yet"}
          </span>
          <span>
            Preparation: {snapshot.prepare_job?.state ?? "No durable worker"}
            {" · "}
            attempts {snapshot.prepare_job?.attempt_count ?? 0}/
            {snapshot.prepare_job?.max_attempts ?? 0}
          </span>
          <span>Final reviews: {snapshot.counts?.final_reviews ?? 0}</span>
          <span>Submit commands: {snapshot.counts?.submit_commands ?? 0}</span>
          <strong>
            Employer submission receipts:{" "}
            {snapshot.counts?.employer_receipts ?? 0}
          </strong>
          {(snapshot.counts?.employer_receipts ?? 0) === 0 && (
            <span className="diagnostic-error">
              No verified employer submission. A click or a filled form is not
              success.
            </span>
          )}
          <strong>What is blocking the next step?</strong>
          {(snapshot.pending_controls?.length ?? 0) > 0 ? (
            <ul>
              {snapshot.pending_controls?.map((control) => (
                <li key={control.control_id}>
                  {control.semantic_type} · {control.control_id} ·{" "}
                  {control.status}
                </li>
              ))}
            </ul>
          ) : (
            <span>No pending normal-answer controls recorded.</span>
          )}
          <strong>Latest durable execution events</strong>
          <ol>
            {snapshot.events?.map((event, i) => (
              <li key={event.occurred_at + "-" + event.event_type + "-" + i}>
                {event.event_type} · {event.occurred_at}
              </li>
            ))}
          </ol>
          <span>
            Values, passwords, OTPs, and résumé content are never transmitted
            through this inspector.
          </span>
        </div>
      )}
    </section>
  );
}
