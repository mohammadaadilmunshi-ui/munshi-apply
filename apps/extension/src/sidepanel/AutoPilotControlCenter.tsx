import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  getAutoPilotStatus,
  pauseAutoPilot,
  requestFilePickerAssist,
  resumeAutoPilot,
  startAutoPilot,
  stopAutoPilot,
  type AutoPilotControllerStatus,
} from "../messaging/client";
import {
  buildAutoPilotLaunchPlan,
  canAutoPilotMakeProgress,
  remainingApprovedFillCount,
  type AutoPilotAnswer,
} from "./autopilot-plan";

export function AutoPilotControlCenter({
  page,
  answers,
  applicationId,
  selectedResumeId,
  selectedResumeSha256,
  nativeAvailable,
  onStatusChange,
}: {
  page: ApplicationPage | null;
  answers: Record<string, AutoPilotAnswer>;
  applicationId: string;
  selectedResumeId: string | null;
  selectedResumeSha256: string | null;
  nativeAvailable: boolean;
  onStatusChange?: (status: AutoPilotControllerStatus | null) => void;
}) {
  const [status, setStatus] = useState<AutoPilotControllerStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const plan = useMemo(
    () =>
      page
        ? buildAutoPilotLaunchPlan(page, answers, {
            expectedResumeSha256: selectedResumeSha256,
          })
        : null,
    [answers, page, selectedResumeSha256],
  );

  const refresh = useCallback(async (): Promise<void> => {
    const next = await getAutoPilotStatus();
    setStatus(next);
    onStatusChange?.(next);
  }, [onStatusChange]);

  useEffect(() => {
    void refresh().catch(() => undefined);
    const timer = window.setInterval(() => {
      void refresh().catch(() => undefined);
    }, 900);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function run(
    action: () => Promise<unknown>,
    success: string,
  ): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await action();
      await refresh();
      setMessage(success);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "AutoPilot action failed",
      );
    } finally {
      setBusy(false);
    }
  }

  const active = status && status.session.status !== "STOPPED";
  const resumable =
    status?.session.status === "PAUSED_OWNER" ||
    status?.session.status === "PAUSED_REVIEW" ||
    status?.session.status === "PAUSED_SECURITY";
  const pausable =
    status?.session.status === "RUNNING" ||
    status?.session.status === "WAITING_RESCAN" ||
    status?.session.status === "WAITING_NAVIGATION";
  const pauseQueued = status?.ownerPauseRequested === true;
  const completedControlIds = status?.session.completedControlIds ?? [];
  const remainingApprovedFillCountValue = plan
    ? remainingApprovedFillCount(plan, completedControlIds)
    : 0;
  const safeProgressAvailable = Boolean(
    plan &&
      !plan.preflight.canAct &&
      canAutoPilotMakeProgress(plan, completedControlIds),
  );
  const canProgress = Boolean(
    plan && canAutoPilotMakeProgress(plan, completedControlIds),
  );

  return (
    <section>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Owner-operated application runtime</p>
          <h2>AutoPilot Control Center</h2>
        </div>
        <span className={active ? "badge" : "badge review"}>
          {status?.session.status ?? "IDLE"}
        </span>
      </div>

      {!nativeAvailable && (
        <div className="safety-callout">
          <strong>Native companion required</strong>
          <span>
            Durable checkpoints are required before AutoPilot may navigate.
          </span>
        </div>
      )}

      {page ? (
        <>
          <p className="url">{new URL(page.url).hostname}</p>
          <div className="metrics">
            <article>
              <strong>{status?.session.completedControlIds.length ?? 0}</strong>
              <span>completed</span>
            </article>
            <article>
              <strong>
                {status?.session.pendingControlIds.length ??
                  plan?.fillInstructions.length ??
                  0}
              </strong>
              <span>pending</span>
            </article>
            <article>
              <strong>{status?.session.lastCheckpointSequence ?? -1}</strong>
              <span>checkpoint</span>
            </article>
          </div>

          <div className="cloud-connection">
            <strong>
              Current page: {page.applicationState.replaceAll("_", " ")}
            </strong>
            <span>Waiting for: {status?.waitingFor ?? "none"}</span>
            {pauseQueued && (
              <span className="diagnostic-error">
                Pause requested · current action will verify before AutoPilot
                stops
              </span>
            )}
            {status?.pendingDraftUsageId && (
              <span className="diagnostic-error">
                Recording approved AI-answer usage before continuing
              </span>
            )}
            {status?.lastFillResult && (
              <span>
                Last verified autofill:{" "}
                {status.lastFillResult.strategy ?? "guarded"}
                {status.lastFillResult.rebound ? " · self-healed binding" : ""}
                {status.lastFillResult.stabilized === false
                  ? " · DOM still changing at timeout"
                  : ""}
              </span>
            )}
            <span>
              Last verified page: {status?.session.lastPageId ?? "not started"}
            </span>
            <span>
              Résumé binding:{" "}
              {status?.session.selectedResumeId ?? selectedResumeId ?? "none"}
            </span>
            {status?.session.pauseReason && (
              <span className="diagnostic-error">
                {status.session.pauseReason}
              </span>
            )}
            {status?.session.securityCheckpoint && (
              <span className="diagnostic-error">
                Owner action required:{" "}
                {status.session.securityCheckpoint.replaceAll("_", " ")}
              </span>
            )}
          </div>

          {plan && (
            <div className="cloud-connection">
              <strong>Live pre-flight: {plan.preflight.state}</strong>
              <span>{plan.preflight.readyCount} approved fill actions</span>
              <span>
                {plan.preflight.reviewCount} require review/manual interaction
              </span>
              <span>
                {plan.preflight.unresolvedCount} required answers unresolved
              </span>
              {safeProgressAvailable && (
                <span>
                  Safe-progress mode: MUNSHI can fill{" "}
                  {remainingApprovedFillCountValue} approved field
                  {remainingApprovedFillCountValue === 1 ? "" : "s"}, then it
                  will pause before navigation for the remaining review.
                </span>
              )}
              {plan.optionalUnansweredCount > 0 && (
                <span>
                  {plan.optionalUnansweredCount} optional questions left blank
                </span>
              )}
            </div>
          )}

          {plan?.manualControls.length ? (
            <div className="answer-list">
              <h3>Manual browser handoff</h3>
              {plan.manualControls.map((control) => (
                <article className="answer-card" key={control.controlId}>
                  <strong>
                    {control.label || control.name || "Manual control"}
                  </strong>
                  <span>{control.kind.replaceAll("_", " ")}</span>
                  {control.validationMessage && (
                    <span className="diagnostic-error">
                      {control.validationMessage}
                    </span>
                  )}
                  {control.kind === "FILE" ? (
                    <button
                      className="quiet"
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void run(
                          () =>
                            requestFilePickerAssist(
                              control.frameId,
                              control.controlId,
                            ),
                          "Employer file picker requested. Choose the file yourself; MUNSHI will continue only after a fresh scan confirms a selection.",
                        )
                      }
                    >
                      Open employer file picker
                    </button>
                  ) : (
                    <span className="diagnostic-error">
                      This required control is not safe for autonomous
                      interaction.
                    </span>
                  )}
                </article>
              ))}
            </div>
          ) : null}

          <div className="record-actions">
            <button
              className="primary"
              type="button"
              disabled={
                busy || !nativeAvailable || !canProgress || Boolean(active)
              }
              onClick={() =>
                void run(
                  () =>
                    startAutoPilot({
                      applicationId,
                      preflight: plan!.preflight,
                      fillInstructions: plan!.fillInstructions,
                      selectedResumeId,
                      selectedResumeSha256,
                    }),
                  plan!.preflight.canAct
                    ? "AutoPilot started with the current verified pre-flight state."
                    : "AutoPilot started in safe-progress mode. Approved fields will fill first; MUNSHI will pause before navigation for unresolved or review-required items.",
                )
              }
            >
              Start AutoPilot
            </button>
            <button
              className="quiet"
              type="button"
              disabled={busy || !pausable || pauseQueued}
              onClick={() =>
                void run(
                  () => pauseAutoPilot(),
                  "Pause requested. MUNSHI will finish verifying any in-flight action, persist a checkpoint, and stop before the next action.",
                )
              }
            >
              Pause
            </button>
            <button
              className="quiet"
              type="button"
              disabled={busy || !resumable || !canProgress}
              onClick={() =>
                void run(
                  () =>
                    resumeAutoPilot({
                      preflight: plan!.preflight,
                      fillInstructions: plan!.fillInstructions,
                    }),
                  plan!.preflight.canAct
                    ? "AutoPilot resumed from its durable application state."
                    : "AutoPilot resumed in safe-progress mode for remaining approved fields; navigation remains blocked until review is complete.",
                )
              }
            >
              Resume
            </button>
            <button
              className="quiet destructive"
              type="button"
              disabled={busy || !status || status.session.status === "STOPPED"}
              onClick={() =>
                void run(() => stopAutoPilot(), "AutoPilot stopped by owner.")
              }
            >
              Stop
            </button>
          </div>
        </>
      ) : (
        <p>Open an application page to prepare AutoPilot.</p>
      )}

      {message && <div className="notice">{message}</div>}
      <div className="safety-callout">
        <strong>Permanent owner boundaries</strong>
        <span>
          AutoPilot never performs final submission, CAPTCHA, MFA, OTP, identity
          verification, authentication, or OS file selection. Those actions
          pause or hand control to you.
        </span>
      </div>
    </section>
  );
}
