import { useMemo, useState, type DragEvent } from "react";
import {
  getCloudConnection,
  uploadEncryptedResume,
  type CloudSnapshot,
  type ResumeRecord,
} from "../storage/cloud";
import {
  classifyEncryptedResume,
  deleteEncryptedResume,
  resumeFamilyFor,
  resumeKindLabel,
  type ResumeVaultSource,
} from "../storage/resume-vault";

const acceptedResumeTypes =
  ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function ResumeVaultPanel({
  snapshot,
  selectedResumeId,
  currentRole,
  onSelected,
  onRefresh,
  onNotice,
}: {
  snapshot: CloudSnapshot | null;
  selectedResumeId: string;
  currentRole: string | null;
  onSelected: (resumeId: string) => void;
  onRefresh: () => Promise<void>;
  onNotice: (message: string) => void;
}) {
  const [source, setSource] = useState<ResumeVaultSource>("MASTER");
  const [roleFamily, setRoleFamily] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  const resumes = useMemo(
    () =>
      [...(snapshot?.resumes ?? [])].sort((left, right) => {
        const leftRank = left.source === "MASTER" ? 0 : left.source === "TAILORED" ? 1 : 2;
        const rightRank =
          right.source === "MASTER" ? 0 : right.source === "TAILORED" ? 1 : 2;
        return leftRank - rightRank || right.addedAt.localeCompare(left.addedAt);
      }),
    [snapshot],
  );

  function effectiveRoleFamily(): string | null {
    if (source !== "TAILORED") return null;
    return roleFamily.trim() || currentRole?.trim() || "Current job";
  }

  async function upload(file: File | null): Promise<void> {
    if (!file || busy) return;
    const connection = await getCloudConnection();
    if (!connection) {
      onNotice("Pair this Edge installation before adding a résumé.");
      return;
    }
    const role = effectiveRoleFamily();
    setBusy(true);
    try {
      const resume = await uploadEncryptedResume(connection, file, {
        source,
        family: resumeFamilyFor(source, role),
        roleFamily: role,
      });
      onSelected(resume.resumeId);
      if (source === "TAILORED") setRoleFamily("");
      onNotice(
        `${resume.name} encrypted as ${source === "MASTER" ? "your master résumé" : `a tailored résumé for ${role ?? "this job"}`}.`,
      );
      await onRefresh();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Résumé upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function classify(
    resume: ResumeRecord,
    nextSource: "MASTER" | "TAILORED",
  ): Promise<void> {
    const connection = await getCloudConnection();
    if (!connection || busy) return;
    const role =
      nextSource === "TAILORED"
        ? roleFamily.trim() || currentRole?.trim() || "Current job"
        : null;
    setBusy(true);
    try {
      await classifyEncryptedResume(connection, resume, {
        source: nextSource,
        roleFamily: role,
      });
      onNotice(
        nextSource === "MASTER"
          ? `${resume.name} is now classified as a master résumé.`
          : `${resume.name} is now tailored for ${role}.`,
      );
      await onRefresh();
    } catch (error) {
      onNotice(
        error instanceof Error ? error.message : "Résumé classification failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove(resume: ResumeRecord): Promise<void> {
    if (busy) return;
    const warning =
      resume.source === "MASTER"
        ? `Remove master résumé ${resume.name}? This removes it from the encrypted vault across devices.`
        : `Remove ${resume.name} from the encrypted vault?`;
    if (!window.confirm(warning)) return;
    const connection = await getCloudConnection();
    if (!connection) return;
    setBusy(true);
    try {
      await deleteEncryptedResume(connection, resume);
      if (selectedResumeId === resume.resumeId) onSelected("");
      onNotice(`${resume.name} removed from the active encrypted résumé vault.`);
      await onRefresh();
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Résumé removal failed");
      await onRefresh().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  function acceptDrop(event: DragEvent<HTMLLabelElement>): void {
    event.preventDefault();
    setDragging(false);
    void upload(event.dataTransfer.files?.[0] ?? null);
  }

  return (
    <div className="resume-vault resume-vault-manager">
      <div className="resume-vault-heading">
        <div>
          <h3>Résumé vault</h3>
          <p>
            Keep a durable master résumé and temporary job/niche versions. Each
            file remains encrypted before synchronization.
          </p>
        </div>
        <span className="badge">{resumes.length} saved</span>
      </div>

      <div className="resume-vault-controls">
        <label>
          <span>Uploading as</span>
          <select
            value={source}
            disabled={busy}
            onChange={(event) =>
              setSource(event.target.value as ResumeVaultSource)
            }
          >
            <option value="MASTER">Master résumé</option>
            <option value="TAILORED">Job / niche résumé</option>
          </select>
        </label>
        {source === "TAILORED" && (
          <label>
            <span>Job / niche label</span>
            <input
              type="text"
              value={roleFamily}
              disabled={busy}
              placeholder={currentRole || "e.g. People Analytics"}
              onChange={(event) => setRoleFamily(event.target.value)}
            />
          </label>
        )}
      </div>

      <label
        className={`resume-upload resume-dropzone${dragging ? " dragging" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          setDragging(true);
        }}
        onDragLeave={(event) => {
          if (event.currentTarget.contains(event.relatedTarget as Node | null))
            return;
          setDragging(false);
        }}
        onDrop={acceptDrop}
      >
        <strong>{busy ? "Encrypting résumé…" : "Drop résumé here"}</strong>
        <span>or click to choose PDF, DOC, or DOCX · maximum 12 MB</span>
        <input
          type="file"
          accept={acceptedResumeTypes}
          disabled={busy}
          onChange={(event) => {
            void upload(event.target.files?.[0] ?? null);
            event.currentTarget.value = "";
          }}
        />
      </label>

      <div className="resume-list managed-resume-list">
        {resumes.length === 0 && (
          <p className="record-empty">No encrypted résumés saved yet.</p>
        )}
        {resumes.map((resume) => (
          <article
            className={`managed-resume-card${selectedResumeId === resume.resumeId ? " selected" : ""}`}
            key={resume.resumeId}
          >
            <div className="managed-resume-heading">
              <div>
                <strong>{resume.name}</strong>
                <span>{resumeKindLabel(resume)}</span>
              </div>
              {selectedResumeId === resume.resumeId && (
                <span className="badge">Selected</span>
              )}
            </div>
            <span>
              {Math.ceil(resume.sizeBytes / 1024)} KB · encrypted · v
              {resume.version ?? 1}
            </span>
            <div className="record-actions managed-resume-actions">
              <button
                className="quiet"
                type="button"
                disabled={busy || selectedResumeId === resume.resumeId}
                onClick={() => onSelected(resume.resumeId)}
              >
                Use for application
              </button>
              {resume.source !== "MASTER" && (
                <button
                  className="quiet"
                  type="button"
                  disabled={busy}
                  onClick={() => void classify(resume, "MASTER")}
                >
                  Set as master
                </button>
              )}
              {resume.source !== "TAILORED" && (
                <button
                  className="quiet"
                  type="button"
                  disabled={busy}
                  onClick={() => void classify(resume, "TAILORED")}
                >
                  Make job / niche
                </button>
              )}
              <button
                className="quiet destructive"
                type="button"
                disabled={busy}
                onClick={() => void remove(resume)}
              >
                Remove
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
