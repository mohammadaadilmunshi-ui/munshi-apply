"use client";

import { useEffect, useState } from "react";
import { ensureWorkspaceKey } from "./vault-client";

type WorkspaceStatus = {
  id: string;
  status: string;
  devices: number;
  encryptedObjects: number;
  events: number;
  conflicts: number;
};

type PairingChallenge = {
  id: string;
  secret: string;
  expiresAt: string;
};

export function WorkspacePanel({ ownerName }: { ownerName: string }) {
  const [workspace, setWorkspace] = useState<WorkspaceStatus | null>(null);
  const [challenge, setChallenge] = useState<PairingChallenge | null>(null);
  const [status, setStatus] = useState("Checking encrypted workspace…");
  const [busy, setBusy] = useState(false);
  const [workspaceKey, setWorkspaceKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      fetch("/api/workspace", {
        headers: { accept: "application/json" },
      }),
      ensureWorkspaceKey(),
    ])
      .then(async ([response, key]) => {
        const payload = (await response.json()) as {
          workspace?: WorkspaceStatus;
          error?: string;
        };
        if (!response.ok || !payload.workspace) {
          throw new Error(payload.error ?? "Workspace is unavailable.");
        }
        if (!cancelled) {
          setWorkspace(payload.workspace);
          setWorkspaceKey(key);
          setStatus("Encrypted cloud workspace ready");
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setStatus(
            error instanceof Error ? error.message : "Workspace unavailable",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function createPairingChallenge() {
    setBusy(true);
    setChallenge(null);
    try {
      const response = await fetch("/api/pairing", { method: "POST" });
      const payload = (await response.json()) as {
        challenge?: PairingChallenge;
        error?: string;
      };
      if (!response.ok || !payload.challenge) {
        throw new Error(payload.error ?? "Unable to create pairing challenge.");
      }
      setChallenge(payload.challenge);
      setStatus("One-time pairing challenge created");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Pairing failed");
    } finally {
      setBusy(false);
    }
  }

  async function copyPairingBundle() {
    if (!challenge || !workspaceKey) return;
    try {
      await navigator.clipboard.writeText(
        JSON.stringify({
          challengeId: challenge.id,
          secret: challenge.secret,
          workspaceKey,
          encryptionVersion: 1,
        }),
      );
      setStatus(
        "Pairing code copied. Paste it only in MUNSHI Apply Diagnostics; it expires in 10 minutes.",
      );
    } catch {
      setStatus(
        "Unable to copy the pairing code. Try again from this workspace.",
      );
    }
  }

  return (
    <section
      id="workspace"
      className="section-block workspace-block"
      aria-labelledby="workspace-title"
    >
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Owner workspace</p>
          <h2 id="workspace-title">Secure cross-device control</h2>
        </div>
        <span className="last-check">Signed in as {ownerName}</span>
      </div>

      <div className="workspace-grid">
        <article className="control-card">
          <div className="control-card-heading">
            <div>
              <span>Cloud authority</span>
              <strong>{status}</strong>
            </div>
            <i
              className={workspace ? "online" : "pending"}
              aria-hidden="true"
            />
          </div>
          <div className="workspace-metrics">
            <div>
              <strong>{workspace?.devices ?? "—"}</strong>
              <span>active devices</span>
            </div>
            <div>
              <strong>{workspace?.encryptedObjects ?? "—"}</strong>
              <span>encrypted files</span>
            </div>
            <div>
              <strong>{workspace?.events ?? "—"}</strong>
              <span>sync events</span>
            </div>
            <div>
              <strong>{workspace?.conflicts ?? "—"}</strong>
              <span>sync conflicts</span>
            </div>
          </div>
          <p>
            Résumés, profile facts, and application checkpoints are encrypted in
            your browser before upload. The server stores ciphertext and
            checksums, not plaintext values.
          </p>
          <a className="button secondary workspace-launch" href="/workspace">
            Open encrypted workspace
          </a>
        </article>

        <article className="control-card pairing-card">
          <div>
            <span>Device enrollment</span>
            <h3>Pair one Edge installation</h3>
            <p>
              Use a new code to pair another Edge installation or to enable
              end-to-end encryption on an installation that is already paired.
            </p>
          </div>
          {challenge ? (
            <div className="pairing-result" role="status">
              <span>
                Code ready until{" "}
                {new Date(challenge.expiresAt).toLocaleTimeString()}
              </span>
              <ol>
                <li>Use the button below to copy the one-time pairing code.</li>
                <li>
                  In MUNSHI Apply → Diagnostics, paste it into “One-time pairing
                  bundle”, then choose “Pair device.”
                </li>
              </ol>
              <p>Never paste this code into chat or send it to anyone.</p>
              <button
                type="button"
                className="button primary"
                onClick={() => void copyPairingBundle()}
              >
                Copy pairing code
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="button primary"
              disabled={busy || !workspace || !workspaceKey}
              onClick={() => void createPairingChallenge()}
            >
              {busy ? "Creating…" : "Create one-time pairing code"}
            </button>
          )}
        </article>
      </div>
    </section>
  );
}
