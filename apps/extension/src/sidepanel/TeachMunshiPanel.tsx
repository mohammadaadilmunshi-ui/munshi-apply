import { useEffect, useMemo, useState } from "react";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  beginTeachMunshi,
  cancelTeachMunshi,
  finishTeachMunshi,
  type TeachMunshiStart,
} from "../messaging/client";

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

  async function start(): Promise<void> {
    const control = eligible.find((item) => item.controlId === selected);
    if (!control) return;
    setBusy(true);
    setMessage("");
    try {
      const session = await beginTeachMunshi(
        control.frameId,
        control.controlId,
        applicationId,
      );
      setActive(session);
      setMessage(
        "Teaching is recording interaction mechanics only. Complete this one control on the employer page, then click Learn this interaction.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Teach MUNSHI could not start",
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
    try {
      const learned = await finishTeachMunshi(
        control.frameId,
        active.sessionId,
        applicationId,
      );
      setActive(null);
      if (!learned.reusable || !learned.recipe) {
        setMessage(
          learned.quality
            ? `MUNSHI observed the interaction, but capture quality was ${Math.round(learned.quality.score * 100)}%. Retry the one control slowly so its committed before/after state is visible; the application remains unblocked.`
            : "MUNSHI observed the interaction but could not infer a reusable safe recipe. You can continue manually; the application was not blocked.",
        );
        return;
      }
      const quality = learned.quality
        ? ` · capture ${Math.round(learned.quality.score * 100)}%`
        : "";
      setMessage(
        `Candidate recipe v${learned.recipe.version} saved in ${learned.recipe.state.toLowerCase()} mode${quality}. MUNSHI will try it on the matching control and promote it after verified success.`,
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Teach MUNSHI could not save the demonstration",
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
      setMessage(
        "Teaching cancelled. Nothing was learned from that demonstration.",
      );
      setBusy(false);
    }
  }

  return (
    <div className="cloud-connection">
      <strong>Teach MUNSHI</strong>
      <span>
        When a control does not work, show MUNSHI the interaction once. It
        stores the mechanics, not the answer you selected.
      </span>
      {eligible.length > 0 ? (
        <>
          <label>
            Control to teach
            <select
              value={active?.controlId ?? selected}
              disabled={busy || Boolean(active)}
              onChange={(event) => setSelected(event.target.value)}
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
              className="quiet"
              type="button"
              disabled={busy || !nativeAvailable || !selected}
              onClick={() => void start()}
            >
              Teach selected control
            </button>
          ) : (
            <div className="record-actions">
              <button
                className="primary"
                type="button"
                disabled={busy}
                onClick={() => void finish()}
              >
                Learn this interaction
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
          )}
        </>
      ) : (
        <span>No teachable controls are visible on this page.</span>
      )}
      {message && (
        <span className={active ? "diagnostic-error" : ""}>{message}</span>
      )}
    </div>
  );
}
