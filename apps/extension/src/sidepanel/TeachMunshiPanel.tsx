import { useEffect, useMemo, useState } from "react";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  beginTeachMunshi,
  cancelTeachMunshi,
  finishTeachMunshi,
  type TeachMunshiStart,
} from "../messaging/client";

type ResultTone = "success" | "warning" | "error" | null;

export function TeachMunshiPanel({
  page,
  applicationId,
  nativeAvailable,
  suggestedControlId,
}: {
  page: ApplicationPage;
  applicationId: string;
  nativeAvailable: boolean;
  suggestedControlId: string | null;
}) {
  const eligible = useMemo(
    () =>
      page.controls.filter(
        (control) =>
          control.visible &&
          !control.disabled &&
          !["FILE", "BUTTON"].includes(control.kind),
      ),
    [page.controls],
  );
  const [selected, setSelected] = useState("");
  const [active, setActive] = useState<TeachMunshiStart | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [resultTone, setResultTone] = useState<ResultTone>(null);

  useEffect(() => {
    if (active) return;
    if (
      suggestedControlId &&
      eligible.some((item) => item.controlId === suggestedControlId)
    ) {
      setSelected(suggestedControlId);
      return;
    }
    if (!eligible.some((item) => item.controlId === selected)) {
      setSelected(eligible[0]?.controlId ?? "");
    }
  }, [active, eligible, selected, suggestedControlId]);

  const labelFor = (controlId: string): string => {
    const control = eligible.find((item) => item.controlId === controlId);
    if (!control) return controlId;
    const question = page.questions.find(
      (item) => item.controlId === controlId,
    );
    return (
      question?.rawText ||
      control.label ||
      control.ariaLabel ||
      control.name ||
      control.kind
    );
  };

  const selectedLabel = active
    ? labelFor(active.controlId)
    : selected
      ? labelFor(selected)
      : "";

  async function start(): Promise<void> {
    const control = eligible.find((item) => item.controlId === selected);
    if (!control) return;
    setBusy(true);
    setMessage("");
    setResultTone(null);
    try {
      const session = await beginTeachMunshi(
        control.frameId,
        control.controlId,
        applicationId,
      );
      setActive(session);
    } catch (error) {
      setResultTone("error");
      setMessage(
        error instanceof Error ? error.message : "MUNSHI could not start watching this field.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function finish(): Promise<void> {
    if (!active) return;
    const control = eligible.find(
      (item) => item.controlId === active.controlId,
    );
    if (!control) return;
    setBusy(true);
    setMessage("");
    setResultTone(null);
    try {
      const learned = await finishTeachMunshi(
        control.frameId,
        active.sessionId,
        applicationId,
      );
      setActive(null);

      if (!learned.reusable || !learned.recipe) {
        const quality = learned.quality
          ? Math.round(learned.quality.score * 100)
          : null;
        if (quality === 0) {
          setResultTone("error");
          setMessage(
            "I did not see the interaction, so nothing was learned. Start again, wait until MUNSHI says Watching, then complete only that field on the employer page before returning here.",
          );
        } else {
          setResultTone("warning");
          setMessage(
            quality === null
              ? "I saw the interaction, but not enough of it to save a safe lesson. Nothing was learned; you can continue the application manually."
              : `I saw part of the interaction (${quality}% confidence), but not enough to save a safe lesson. Retry once, starting before you touch the field.`,
          );
        }
        return;
      }

      const quality = learned.quality
        ? Math.round(learned.quality.score * 100)
        : null;
      setResultTone("success");
      setMessage(
        `Lesson captured${quality === null ? "" : ` with ${quality}% confidence`}. MUNSHI saved it in testing mode and will trust it only after a future matching control is completed and verified successfully.`,
      );
    } catch (error) {
      setResultTone("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "MUNSHI could not finish learning this interaction.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancel(): Promise<void> {
    if (!active) return;
    const control = eligible.find(
      (item) => item.controlId === active.controlId,
    );
    setBusy(true);
    try {
      if (control) await cancelTeachMunshi(control.frameId, active.sessionId);
    } finally {
      setActive(null);
      setResultTone("warning");
      setMessage("Teaching cancelled. Nothing from this demonstration was saved.");
      setBusy(false);
    }
  }

  return (
    <div className="teach-panel" aria-labelledby="teach-munshi-heading">
      <div className="teach-header">
        <div>
          <p className="eyebrow">Learning mode</p>
          <h3 id="teach-munshi-heading">Teach MUNSHI</h3>
        </div>
        <span className={active ? "badge review" : "badge"}>
          {active ? "Watching" : "Ready"}
        </span>
      </div>

      <p className="teach-copy">
        Use this only when MUNSHI struggles with a field. You demonstrate how the
        control works once; MUNSHI learns the interaction mechanics, never the
        answer you selected.
      </p>

      {eligible.length > 0 ? (
        <>
          {!active && (
            <ol className="teach-steps">
              <li>Choose the field MUNSHI had trouble with.</li>
              <li>Start watching before you touch the employer field.</li>
              <li>Complete that one field, return here, then finish teaching.</li>
            </ol>
          )}

          <label className="teach-field">
            <span>Field to teach</span>
            <select
              value={active?.controlId ?? selected}
              disabled={busy || Boolean(active)}
              onChange={(event) => {
                setSelected(event.target.value);
                setMessage("");
                setResultTone(null);
              }}
            >
              {eligible.map((control) => (
                <option key={control.controlId} value={control.controlId}>
                  {labelFor(control.controlId)}
                </option>
              ))}
            </select>
          </label>

          {!active ? (
            <button
              className="primary teach-start"
              type="button"
              disabled={busy || !nativeAvailable || !selected}
              onClick={() => void start()}
            >
              {busy ? "Starting…" : "Start watching this field"}
            </button>
          ) : (
            <div className="teach-live" role="status" aria-live="polite">
              <div className="teach-live-heading">
                <span className="teach-pulse" aria-hidden="true" />
                Watching now
              </div>
              <strong>{selectedLabel}</strong>
              <p>
                Go to the employer page and complete this one field normally.
                When the value is visibly selected or entered, return here.
              </p>
              <div className="record-actions">
                <button
                  className="primary teach-finish"
                  type="button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {busy ? "Checking what I saw…" : "Finish & learn"}
                </button>
                <button
                  className="quiet"
                  type="button"
                  disabled={busy}
                  onClick={() => void cancel()}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="inline-note warning">
          No teachable fields are visible on this page yet. Open the part of the
          employer form that contains the field and return here.
        </div>
      )}

      {!nativeAvailable && (
        <div className="inline-note warning">
          Teaching needs the MUNSHI native companion. Open Diagnostics if the
          companion is not connected.
        </div>
      )}

      {message && (
        <div className={`teach-result ${resultTone ?? "warning"}`} role="status">
          {message}
        </div>
      )}
    </div>
  );
}
