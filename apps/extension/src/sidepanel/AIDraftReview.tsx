import { useCallback, useEffect, useMemo, useState } from "react";
import type { Question } from "@munshi-apply/contracts";
import {
  approveAIDraft,
  generateAIDraft,
  getAIControlStatus,
  getApprovedAIDraft,
  listAIDrafts,
  previewAIDraft,
  rejectAIDraft,
  updateAIDraft,
  type AIDraftPreview,
  type AIDraftRecord,
} from "../messaging/native";

export function AIDraftReview({
  applicationId,
  pageId,
  question,
  nativeAvailable,
  onApproved,
}: {
  applicationId: string;
  pageId: string;
  question: Question;
  nativeAvailable: boolean;
  onApproved: (value: string, draftId: string) => void;
}) {
  const [draft, setDraft] = useState<AIDraftRecord | null>(null);
  const [preview, setPreview] = useState<AIDraftPreview | null>(null);
  const [safe, setSafe] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const request = useMemo(
    () => ({
      applicationId,
      pageId,
      questionId: question.questionId,
      controlId: question.controlId,
      question: question.rawText,
      semanticType: question.semanticType,
      correlationId: `draft-${question.questionId}`,
      maxWords: 250,
      maxOutputTokens: 768,
    }),
    [
      applicationId,
      pageId,
      question.controlId,
      question.questionId,
      question.rawText,
      question.semanticType,
    ],
  );

  const refresh = useCallback(async () => {
    if (!nativeAvailable) return;
    const [control, rows, approved] = await Promise.all([
      getAIControlStatus(),
      listAIDrafts(applicationId, pageId),
      getApprovedAIDraft(request),
    ]);
    setSafe(
      control.guardrails.safeDraftSemanticTypes.includes(question.semanticType),
    );
    const latest = rows.find(
      (row) =>
        row.questionId === question.questionId &&
        row.controlId === question.controlId,
    );
    const selected = approved ?? latest ?? null;
    setDraft(selected);
    setText(selected?.currentText ?? "");
  }, [
    applicationId,
    nativeAvailable,
    pageId,
    question.controlId,
    question.questionId,
    question.semanticType,
    request,
  ]);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  async function previewRequest(): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const next = await previewAIDraft(request);
      setPreview(next);
      setMessage(
        "Provider-free preview passed. No model request or spend occurred.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "AI draft preview failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function generate(): Promise<void> {
    setBusy(true);
    setMessage("Generating an evidence-grounded draft…");
    try {
      const result = await generateAIDraft(request);
      setDraft(result.draft);
      setText(result.draft.currentText);
      setPreview(null);
      setMessage(
        "Draft generated and validated. It is not approved for filling yet.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "AI generation failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(): Promise<void> {
    if (!draft || text === draft.currentText) return;
    setBusy(true);
    try {
      const next = await updateAIDraft(
        draft.draftId,
        text,
        draft.contentSha256,
      );
      setDraft(next);
      setText(next.currentText);
      setMessage(
        "Owner edit saved. Any previous approval is invalidated until you approve this exact text.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Unable to save draft edit",
      );
    } finally {
      setBusy(false);
    }
  }

  async function approve(): Promise<void> {
    if (!draft) return;
    setBusy(true);
    try {
      let current = draft;
      if (text !== draft.currentText) {
        current = await updateAIDraft(draft.draftId, text, draft.contentSha256);
      }
      const approved = await approveAIDraft(
        current.draftId,
        current.contentSha256,
      );
      setDraft(approved);
      setText(approved.currentText);
      onApproved(approved.currentText, approved.draftId);
      setMessage(
        "Exact draft approved for this application question and made eligible for guarded fill.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Unable to approve AI draft",
      );
    } finally {
      setBusy(false);
    }
  }

  async function reject(): Promise<void> {
    if (!draft) return;
    setBusy(true);
    try {
      const rejected = await rejectAIDraft(draft.draftId);
      setDraft(rejected);
      setText(rejected.currentText);
      setMessage("Draft rejected. It is not eligible for guarded fill.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Unable to reject AI draft",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!nativeAvailable || !safe || question.sensitive) return null;

  return (
    <div className="cloud-pairing">
      <div className="answer-heading">
        <div>
          <strong>AI draft review</strong>
          <span>Evidence-grounded · owner approval required</span>
        </div>
        <span
          className={
            draft?.status === "APPROVED" || draft?.status === "USED"
              ? "badge"
              : "badge review"
          }
        >
          {draft?.status ?? "NOT GENERATED"}
        </span>
      </div>

      {!draft && (
        <div className="record-actions">
          <button
            className="quiet"
            type="button"
            disabled={busy}
            onClick={() => void previewRequest()}
          >
            Preview evidence & cost
          </button>
          <button
            className="primary"
            type="button"
            disabled={busy}
            onClick={() => void generate()}
          >
            Generate draft
          </button>
        </div>
      )}

      {preview && (
        <div className="cloud-connection">
          <strong>{preview.model}</strong>
          <span>{preview.evidenceIds.length} authoritative evidence items</span>
          <span>Planned maximum: ${preview.plannedCostUsd.toFixed(6)}</span>
          <span>Budget gate: {preview.budget.state}</span>
          <button
            className="primary"
            type="button"
            disabled={busy}
            onClick={() => void generate()}
          >
            Generate this draft
          </button>
        </div>
      )}

      {draft && (
        <>
          <label>
            <span>Generated / owner-edited answer</span>
            <textarea
              rows={6}
              value={text}
              disabled={
                busy ||
                ["REJECTED", "SUPERSEDED", "USED"].includes(draft.status)
              }
              onChange={(event) => setText(event.target.value)}
            />
          </label>
          <div className="cloud-connection">
            <span>Model: {draft.model}</span>
            <span>Evidence: {draft.evidenceIds.join(", ")}</span>
            <span>
              Usage: {draft.usage.inputTokens} input +{" "}
              {draft.usage.outputTokens} output tokens · $
              {draft.usage.costUsd.toFixed(6)}
            </span>
            <span>Claims validated: {draft.claims.length}</span>
          </div>
          <div className="record-actions">
            <button
              className="quiet"
              type="button"
              disabled={
                busy ||
                text === draft.currentText ||
                ["REJECTED", "SUPERSEDED", "USED"].includes(draft.status)
              }
              onClick={() => void saveEdit()}
            >
              Save edit
            </button>
            <button
              className="primary"
              type="button"
              disabled={
                busy ||
                !text.trim() ||
                ["REJECTED", "SUPERSEDED", "USED"].includes(draft.status) ||
                (draft.status === "APPROVED" && text === draft.currentText)
              }
              onClick={() => void approve()}
            >
              Approve exact answer
            </button>
            {(draft.status === "APPROVED" || draft.status === "USED") && (
              <button
                className="primary"
                type="button"
                disabled={busy}
                onClick={() => onApproved(draft.currentText, draft.draftId)}
              >
                Use approved answer
              </button>
            )}
            <button
              className="quiet"
              type="button"
              disabled={
                busy ||
                ["REJECTED", "SUPERSEDED", "USED"].includes(draft.status)
              }
              onClick={() => void reject()}
            >
              Reject
            </button>
            <button
              className="quiet"
              type="button"
              disabled={busy}
              onClick={() => void generate()}
            >
              Regenerate
            </button>
          </div>
        </>
      )}

      {message && <div className="notice">{message}</div>}
    </div>
  );
}
