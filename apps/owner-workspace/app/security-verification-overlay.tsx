"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  decryptLatestEntities,
  fetchSyncEvents,
  getWorkspaceKey,
  putEncryptedEntity,
  type DecryptedEntity,
} from "./vault-client";

type ChallengeKind =
  | "CAPTCHA"
  | "MFA"
  | "OTP"
  | "IDENTITY_VERIFICATION"
  | "AUTHENTICATION";

type ChallengeStatus =
  | "WAITING_FOR_USER"
  | "VERIFYING"
  | "CLEARED"
  | "SESSION_LOST"
  | "EXPIRED";

type ChallengeState = {
  schemaVersion: 1;
  challengeId: string;
  sessionId: string;
  applicationId: string;
  pageId: string;
  tabId: number;
  deviceId: string;
  url: string;
  title: string;
  pageFingerprint: string;
  checkpoint: ChallengeKind;
  status: ChallengeStatus;
  detectedAt: string;
  updatedAt: string;
  expiresAt: string;
  clearedAt: string | null;
};

type ChallengeAckStatus =
  | "FOCUSED"
  | "REJECTED"
  | "STALE_SESSION"
  | "SESSION_LOST"
  | "CLEARED_AND_RESUMED"
  | "RESUME_BLOCKED";

type ChallengeAck = {
  schemaVersion: 1;
  commandId: string;
  challengeId: string;
  deviceId: string;
  status: ChallengeAckStatus;
  reason: string | null;
  updatedAt: string;
};

const POLL_MS = 2_500;
const COMMAND_TTL_MS = 10 * 60 * 1000;
const CLEARED_VISIBLE_MS = 8_000;
const validKinds = new Set<ChallengeKind>([
  "CAPTCHA",
  "MFA",
  "OTP",
  "IDENTITY_VERIFICATION",
  "AUTHENTICATION",
]);
const validStatuses = new Set<ChallengeStatus>([
  "WAITING_FOR_USER",
  "VERIFYING",
  "CLEARED",
  "SESSION_LOST",
  "EXPIRED",
]);
const validAckStatuses = new Set<ChallengeAckStatus>([
  "FOCUSED",
  "REJECTED",
  "STALE_SESSION",
  "SESSION_LOST",
  "CLEARED_AND_RESUMED",
  "RESUME_BLOCKED",
]);

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function parseChallenge(value: unknown): ChallengeState | null {
  const candidate = record(value);
  if (!candidate) return null;
  if (
    candidate.schemaVersion !== 1 ||
    typeof candidate.challengeId !== "string" ||
    typeof candidate.sessionId !== "string" ||
    typeof candidate.applicationId !== "string" ||
    typeof candidate.pageId !== "string" ||
    !Number.isSafeInteger(candidate.tabId) ||
    typeof candidate.deviceId !== "string" ||
    typeof candidate.url !== "string" ||
    typeof candidate.title !== "string" ||
    typeof candidate.pageFingerprint !== "string" ||
    typeof candidate.checkpoint !== "string" ||
    !validKinds.has(candidate.checkpoint as ChallengeKind) ||
    typeof candidate.status !== "string" ||
    !validStatuses.has(candidate.status as ChallengeStatus) ||
    typeof candidate.detectedAt !== "string" ||
    typeof candidate.updatedAt !== "string" ||
    typeof candidate.expiresAt !== "string" ||
    (candidate.clearedAt !== null && typeof candidate.clearedAt !== "string")
  ) {
    return null;
  }
  return candidate as ChallengeState;
}

function parseAck(value: unknown): ChallengeAck | null {
  const candidate = record(value);
  if (!candidate) return null;
  if (
    candidate.schemaVersion !== 1 ||
    typeof candidate.commandId !== "string" ||
    typeof candidate.challengeId !== "string" ||
    typeof candidate.deviceId !== "string" ||
    typeof candidate.status !== "string" ||
    !validAckStatuses.has(candidate.status as ChallengeAckStatus) ||
    (candidate.reason !== null && typeof candidate.reason !== "string") ||
    typeof candidate.updatedAt !== "string"
  ) {
    return null;
  }
  return candidate as ChallengeAck;
}

function latestChallenge(
  entities: Map<string, DecryptedEntity>,
): ChallengeState | null {
  const candidates = Array.from(entities.entries())
    .filter(([key]) => key.startsWith("SECURITY.CHALLENGE.STATE.V1:"))
    .map(([, entity]) => parseChallenge(entity.value))
    .filter((item): item is ChallengeState => item !== null)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  const candidate = candidates[0] ?? null;
  if (!candidate) return null;
  const expiresAt = Date.parse(candidate.expiresAt);
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return null;
  if (
    candidate.status === "CLEARED" &&
    Date.now() - Date.parse(candidate.updatedAt) > CLEARED_VISIBLE_MS
  ) {
    return null;
  }
  if (candidate.status === "EXPIRED") return null;
  return candidate;
}

function ackForCommand(
  entities: Map<string, DecryptedEntity>,
  commandId: string | null,
): ChallengeAck | null {
  if (!commandId) return null;
  return parseAck(
    entities.get(`SECURITY.CHALLENGE.ACK.V1:${commandId}`)?.value,
  );
}

function checkpointLabel(kind: ChallengeKind): string {
  switch (kind) {
    case "CAPTCHA":
      return "CAPTCHA";
    case "MFA":
      return "Multi-factor authentication";
    case "OTP":
      return "One-time code";
    case "IDENTITY_VERIFICATION":
      return "Identity verification";
    case "AUTHENTICATION":
      return "Sign-in verification";
  }
}

function safeHost(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "employer website";
  }
}

function remainingMinutes(value: string): number {
  return Math.max(0, Math.ceil((Date.parse(value) - Date.now()) / 60_000));
}

export default function SecurityVerificationOverlay() {
  const [challenge, setChallenge] = useState<ChallengeState | null>(null);
  const [commandId, setCommandId] = useState<string | null>(null);
  const [ack, setAck] = useState<ChallengeAck | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latestEntitiesRef = useRef<Map<string, DecryptedEntity>>(new Map());

  const refresh = useCallback(async () => {
    try {
      const rawKey = await getWorkspaceKey();
      if (!rawKey) {
        setChallenge(null);
        setAck(null);
        return;
      }
      const { events } = await fetchSyncEvents(0);
      const entities = await decryptLatestEntities(rawKey, events);
      latestEntitiesRef.current = entities;
      const nextChallenge = latestChallenge(entities);
      setChallenge(nextChallenge);
      setAck(ackForCommand(entities, commandId));
      setError(null);
      if (!nextChallenge || nextChallenge.status === "CLEARED") {
        setMinimized(false);
      }
      if (
        nextChallenge &&
        commandId &&
        ackForCommand(entities, commandId)?.challengeId !== nextChallenge.challengeId
      ) {
        setCommandId(null);
        setAck(null);
      }
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : "Security verification status could not be refreshed.",
      );
    }
  }, [commandId]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  const requestChromium = useCallback(async () => {
    if (!challenge || challenge.status === "SESSION_LOST") return;
    setRequesting(true);
    setError(null);
    try {
      const rawKey = await getWorkspaceKey();
      if (!rawKey) {
        throw new Error(
          "This device does not have the MUNSHI workspace recovery key.",
        );
      }
      const { events } = await fetchSyncEvents(0);
      const entities = await decryptLatestEntities(rawKey, events);
      const current = latestChallenge(entities);
      if (!current || current.challengeId !== challenge.challengeId) {
        throw new Error(
          "This verification request changed on another device. The popup has been refreshed.",
        );
      }
      if (
        current.status !== "WAITING_FOR_USER" &&
        current.status !== "VERIFYING"
      ) {
        throw new Error("This verification request is no longer actionable.");
      }
      const nextCommandId = `challenge-command-${crypto.randomUUID()}`;
      const createdAt = new Date().toISOString();
      await putEncryptedEntity({
        rawKey,
        entityType: "SECURITY.CHALLENGE.COMMAND.V1",
        entityId: nextCommandId,
        baseVersion: 0,
        value: {
          schemaVersion: 1,
          commandId: nextCommandId,
          challengeId: current.challengeId,
          action: "FOCUS_AND_CONTINUE",
          targetDeviceId: current.deviceId,
          sessionId: current.sessionId,
          applicationId: current.applicationId,
          pageId: current.pageId,
          tabId: current.tabId,
          url: current.url,
          pageFingerprint: current.pageFingerprint,
          expectedCheckpoint: current.checkpoint,
          createdAt,
          expiresAt: new Date(Date.now() + COMMAND_TTL_MS).toISOString(),
        },
      });
      setCommandId(nextCommandId);
      setAck(null);
      setMinimized(false);
      await refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Chromium continuation could not be requested.",
      );
    } finally {
      setRequesting(false);
    }
  }, [challenge, refresh]);

  const host = useMemo(
    () => (challenge ? safeHost(challenge.url) : ""),
    [challenge],
  );

  if (!challenge) return null;

  if (minimized) {
    return (
      <button
        type="button"
        onClick={() => setMinimized(false)}
        aria-label="Open security verification"
        style={{
          position: "fixed",
          right: 18,
          bottom: 18,
          zIndex: 2147483000,
          border: "1px solid rgba(245, 158, 11, .45)",
          borderRadius: 999,
          background: "rgba(18, 18, 20, .96)",
          color: "#fff7ed",
          padding: "12px 16px",
          boxShadow: "0 18px 55px rgba(0,0,0,.45)",
          font: "600 14px/1.2 ui-sans-serif, system-ui, sans-serif",
          cursor: "pointer",
        }}
      >
        Verification required · {checkpointLabel(challenge.checkpoint)}
      </button>
    );
  }

  const focused = ack?.status === "FOCUSED";
  const terminalError =
    ack &&
    ["REJECTED", "STALE_SESSION", "SESSION_LOST", "RESUME_BLOCKED"].includes(
      ack.status,
    );
  const cleared =
    challenge.status === "CLEARED" || ack?.status === "CLEARED_AND_RESUMED";
  const verifying = challenge.status === "VERIFYING";
  const sessionLost =
    challenge.status === "SESSION_LOST" || ack?.status === "SESSION_LOST";

  return (
    <div
      role="presentation"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 2147483000,
        display: "grid",
        placeItems: "center",
        padding: 18,
        background: "rgba(0,0,0,.62)",
        backdropFilter: "blur(8px)",
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="munshi-security-title"
        aria-describedby="munshi-security-description"
        style={{
          width: "min(560px, 100%)",
          maxHeight: "min(760px, calc(100vh - 36px))",
          overflow: "auto",
          borderRadius: 24,
          border: "1px solid rgba(255,255,255,.13)",
          background:
            "linear-gradient(180deg, rgba(24,24,27,.99), rgba(9,9,11,.99))",
          color: "#fafafa",
          boxShadow: "0 30px 100px rgba(0,0,0,.6)",
          padding: 24,
          fontFamily: "ui-sans-serif, system-ui, -apple-system, sans-serif",
        }}
      >
        <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
          <div
            aria-hidden="true"
            style={{
              width: 44,
              height: 44,
              flex: "0 0 44px",
              borderRadius: 14,
              display: "grid",
              placeItems: "center",
              background: cleared
                ? "rgba(34,197,94,.15)"
                : "rgba(245,158,11,.15)",
              border: cleared
                ? "1px solid rgba(34,197,94,.35)"
                : "1px solid rgba(245,158,11,.35)",
              fontSize: 21,
            }}
          >
            {cleared ? "✓" : "!"}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                flexWrap: "wrap",
                marginBottom: 7,
              }}
            >
              <span
                style={{
                  borderRadius: 999,
                  padding: "4px 9px",
                  background: "rgba(255,255,255,.08)",
                  color: "#d4d4d8",
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                {checkpointLabel(challenge.checkpoint)}
              </span>
              <span style={{ color: "#71717a", fontSize: 12 }}>
                {remainingMinutes(challenge.expiresAt)} min session window
              </span>
            </div>
            <h2
              id="munshi-security-title"
              style={{ margin: 0, fontSize: 22, lineHeight: 1.2 }}
            >
              {cleared
                ? "Verification complete"
                : sessionLost
                  ? "Chromium session needs attention"
                  : "Security verification required"}
            </h2>
            <p
              id="munshi-security-description"
              style={{
                margin: "9px 0 0",
                color: "#a1a1aa",
                fontSize: 14,
                lineHeight: 1.55,
              }}
            >
              {cleared
                ? "MUNSHI independently detected that the security checkpoint cleared and resumed AutoPilot."
                : sessionLost
                  ? "The exact Chromium tab that was checkpointed is no longer available. MUNSHI will not guess or resume into a different application session."
                  : `MUNSHI paused the application on ${host}. Your progress and AutoPilot checkpoint are preserved. Complete only the employer verification in Chromium; MUNSHI will verify that it cleared and continue automatically.`}
            </p>
          </div>
        </div>

        {!cleared && !sessionLost ? (
          <div
            style={{
              marginTop: 20,
              display: "grid",
              gap: 10,
              padding: 14,
              borderRadius: 16,
              background: "rgba(255,255,255,.035)",
              border: "1px solid rgba(255,255,255,.08)",
              fontSize: 13,
              color: "#d4d4d8",
            }}
          >
            <div>✓ Application state and résumé progress checkpointed</div>
            <div>{focused ? "✓" : "2."} Focus the exact Chromium application tab</div>
            <div>{verifying ? "✓" : "3."} Complete the employer verification yourself</div>
            <div>{verifying ? "…" : "4."} MUNSHI verifies clearance and resumes once</div>
          </div>
        ) : null}

        <div aria-live="polite" style={{ minHeight: 24, marginTop: 14 }}>
          {requesting ? (
            <span style={{ color: "#d4d4d8", fontSize: 13 }}>
              Sending encrypted continuation request to Chromium…
            </span>
          ) : focused ? (
            <span style={{ color: "#86efac", fontSize: 13 }}>
              Chromium received the request and focused the preserved application tab.
            </span>
          ) : verifying ? (
            <span style={{ color: "#fde68a", fontSize: 13 }}>
              Verification appears cleared. MUNSHI is validating the saved session before resuming…
            </span>
          ) : terminalError ? (
            <span style={{ color: "#fca5a5", fontSize: 13 }}>
              {ack?.reason ?? "Chromium could not safely continue this saved session."}
            </span>
          ) : error ? (
            <span style={{ color: "#fca5a5", fontSize: 13 }}>{error}</span>
          ) : null}
        </div>

        {!cleared && !sessionLost ? (
          <button
            type="button"
            onClick={() => void requestChromium()}
            disabled={requesting || verifying}
            style={{
              width: "100%",
              marginTop: 8,
              minHeight: 48,
              border: 0,
              borderRadius: 14,
              background: requesting || verifying ? "#3f3f46" : "#fafafa",
              color: requesting || verifying ? "#a1a1aa" : "#09090b",
              fontSize: 15,
              fontWeight: 800,
              cursor: requesting || verifying ? "default" : "pointer",
            }}
          >
            {focused ? "Focus Chromium again" : "Continue in Chromium"}
          </button>
        ) : null}

        {!cleared ? (
          <button
            type="button"
            onClick={() => setMinimized(true)}
            style={{
              width: "100%",
              marginTop: 8,
              minHeight: 42,
              border: 0,
              background: "transparent",
              color: "#a1a1aa",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Minimize — keep application paused
          </button>
        ) : null}

        <p
          style={{
            margin: "14px 0 0",
            color: "#71717a",
            fontSize: 11,
            lineHeight: 1.5,
          }}
        >
          MUNSHI never treats this button as proof that verification succeeded. It
          resumes only after the paired Chromium worker reports a fresh page snapshot
          with the checkpoint gone and the saved session identity still matching.
        </p>
      </section>
    </div>
  );
}
