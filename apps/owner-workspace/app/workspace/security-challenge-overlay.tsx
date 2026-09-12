"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  challengeLabel,
  deriveSecurityChallenge,
  type SecurityChallengeCheckpoint,
} from "../security-challenge-model";
import {
  decryptLatestEntities,
  fetchSyncEvents,
  getWorkspaceKey,
  type DecryptedEntity,
} from "../vault-client";

type OverlayState =
  | "IDLE"
  | "DETECTED"
  | "OPENED"
  | "CHECKING"
  | "STILL_BLOCKED"
  | "CLEARED"
  | "RECOVERY_REQUIRED"
  | "ERROR";

const POLL_MS = 2_000;
const CLEARED_DISPLAY_MS = 2_500;

function formatTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "recently"
    : parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function SecurityChallengeOverlay() {
  const [challenge, setChallenge] = useState<SecurityChallengeCheckpoint | null>(null);
  const [state, setState] = useState<OverlayState>("IDLE");
  const [message, setMessage] = useState("");
  const cursorRef = useRef(0);
  const entitiesRef = useRef(new Map<string, DecryptedEntity>());
  const previousChallengeRef = useRef<SecurityChallengeCheckpoint | null>(null);
  const loadingRef = useRef(false);
  const clearTimerRef = useRef<number | null>(null);

  const refresh = useCallback(async (manual = false) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    if (manual) setState("CHECKING");
    try {
      const rawKey = await getWorkspaceKey();
      if (!rawKey) {
        setChallenge(null);
        setState("IDLE");
        return;
      }

      const sync = await fetchSyncEvents(cursorRef.current);
      if (sync.events.length > 0) {
        const delta = await decryptLatestEntities(rawKey, sync.events);
        for (const [key, entity] of delta) {
          const existing = entitiesRef.current.get(key);
          if (!existing || existing.event.sequence < entity.event.sequence) {
            entitiesRef.current.set(key, entity);
          }
        }
      }
      cursorRef.current = Math.max(cursorRef.current, sync.nextCursor);

      const next = deriveSecurityChallenge(entitiesRef.current);
      const previous = previousChallengeRef.current;
      previousChallengeRef.current = next;
      setChallenge(next);

      if (!next) {
        if (previous) {
          setState("CLEARED");
          setMessage("Chromium reported that the security checkpoint is cleared. MUNSHI can continue safely.");
          if (clearTimerRef.current !== null) {
            window.clearTimeout(clearTimerRef.current);
          }
          clearTimerRef.current = window.setTimeout(() => {
            setState("IDLE");
            setMessage("");
            clearTimerRef.current = null;
          }, CLEARED_DISPLAY_MS);
        } else {
          setState("IDLE");
          setMessage("");
        }
        return;
      }

      if (clearTimerRef.current !== null) {
        window.clearTimeout(clearTimerRef.current);
        clearTimerRef.current = null;
      }

      if (Date.parse(next.expiresAt) <= Date.now()) {
        setState("RECOVERY_REQUIRED");
        setMessage("This checkpoint expired. Re-open the application from MUNSHI so a fresh browser checkpoint can be created.");
        return;
      }

      const sameCheckpoint =
        previous?.entityId === next.entityId && previous?.sequence === next.sequence;
      if (manual && sameCheckpoint) {
        setState("STILL_BLOCKED");
        setMessage("Chromium still reports the security checkpoint. Complete it in the application tab, then check again.");
      } else if (!sameCheckpoint) {
        setState("DETECTED");
        setMessage("MUNSHI paused before the protected step and saved the application checkpoint.");
      }
    } catch (error) {
      if (previousChallengeRef.current) {
        setState("ERROR");
        setMessage(error instanceof Error ? error.message : "Security checkpoint status could not be refreshed.");
      }
    } finally {
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    const kickoff = window.setTimeout(() => void refresh(false), 0);
    const timer = window.setInterval(() => void refresh(false), POLL_MS);
    return () => {
      window.clearTimeout(kickoff);
      window.clearInterval(timer);
      if (clearTimerRef.current !== null) {
        window.clearTimeout(clearTimerRef.current);
      }
    };
  }, [refresh]);

  if (!challenge && state !== "CLEARED") return null;

  const openChromium = () => {
    if (!challenge) return;
    const opened = window.open(challenge.url, "_blank", "noopener,noreferrer");
    if (!opened) {
      setState("RECOVERY_REQUIRED");
      setMessage("Your browser blocked the verification tab. Allow pop-ups for MUNSHI and try again, or open the application from the Chromium device running MUNSHI Apply.");
      return;
    }
    setState("OPENED");
    setMessage("Verification page opened. Complete only the security check there. MUNSHI is watching for an independently verified clearance.");
  };

  const isCleared = state === "CLEARED";
  const isError = state === "ERROR";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="security-checkpoint-title"
      className="fixed inset-0 z-[100] flex items-end justify-center bg-black/65 p-3 backdrop-blur-sm sm:items-center sm:p-6"
    >
      <section className="w-full max-w-xl rounded-[28px] border border-white/10 bg-neutral-950 p-5 text-white shadow-2xl sm:p-7">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-amber-300">
              {isCleared ? "Verification cleared" : "Action required"}
            </p>
            <h2 id="security-checkpoint-title" className="text-2xl font-semibold tracking-tight">
              {isCleared ? "MUNSHI can continue" : "Security verification required"}
            </h2>
          </div>
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-neutral-300">
            {challenge ? challengeLabel(challenge.kind) : "Checkpoint"}
          </span>
        </div>

        <p className="text-sm leading-6 text-neutral-300">
          {message || "MUNSHI paused the application before a protected verification step."}
        </p>

        {challenge ? (
          <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <span className="text-neutral-500">Application</span>
              <span className="truncate text-right text-neutral-200">{challenge.title}</span>
              <span className="text-neutral-500">Site</span>
              <span className="truncate text-right text-neutral-200">{challenge.origin}</span>
              <span className="text-neutral-500">Detected</span>
              <span className="text-right text-neutral-200">{formatTime(challenge.detectedAt)}</span>
            </div>
          </div>
        ) : null}

        {!isCleared && !isError ? (
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={openChromium}
              className="min-h-12 rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-black transition hover:bg-neutral-200"
            >
              Continue in Chromium
            </button>
            <button
              type="button"
              onClick={() => void refresh(true)}
              disabled={state === "CHECKING"}
              className="min-h-12 rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10 disabled:cursor-wait disabled:opacity-50"
            >
              {state === "CHECKING" ? "Checking Chromium…" : "I completed verification · Check again"}
            </button>
          </div>
        ) : null}

        {!isCleared ? (
          <p className="mt-5 text-xs leading-5 text-neutral-500">
            This button never marks a challenge solved by itself. MUNSHI continues only after the application runtime reports that the same security checkpoint is no longer present. Passwords, verification codes, cookies, and challenge answers are not copied into this popup.
          </p>
        ) : null}
      </section>
    </div>
  );
}
