"""Durable, non-secret trust checkpoints for browser security boundaries.

The core execution/session lifecycle remains authoritative. This sidecar stores
only the minimum non-secret metadata needed to release a hosted worker while a
user completes a legitimate authentication/security step in a user-visible
browser. Raw URLs, query strings, fragments, credentials, cookies, OTP/MFA
values, browser storage, and page text are never persisted here.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .database import Database

WAITING_FOR_USER_AUTH = "WAITING_FOR_USER_AUTH"
TRUST_CHECKPOINT_KINDS = frozenset(
    {"AUTHENTICATION", "CAPTCHA", "MFA", "OTP", "IDENTITY_VERIFICATION"}
)
_PAUSABLE_SESSION_STATES = frozenset(
    {
        "SESSION_STARTING",
        "JOB_VERIFIED",
        "FORM_DISCOVERED",
        "PREPARING",
        "NEEDS_INPUT",
        "READY_FOR_REVIEW",
        "READY_TO_SUBMIT",
    }
)
_WAITABLE_JOB_STATES = frozenset({"QUEUED", "RUNNING", "WAITING_INPUT"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_location(url: str) -> tuple[str, str]:
    """Return origin + path digest while discarding query and fragment."""
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("Trust checkpoint URL must be HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("Trust checkpoint URL cannot contain credentials")
    host = parsed.hostname.casefold().rstrip(".")
    port = parsed.port
    origin = f"https://{host}"
    if port is not None and port != 443:
        origin += f":{port}"
    return origin, _sha_text(parsed.path or "/")


def _event_id() -> str:
    return f"trust-event-{uuid4()}"


class TrustCheckpointStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _normalize_kind(value: Any) -> str:
        kind = str(value or "").strip().upper()
        if kind not in TRUST_CHECKPOINT_KINDS:
            raise ValueError("Unsupported browser trust checkpoint")
        return kind

    @staticmethod
    def _wire(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "trust_checkpoint_id": str(row["trust_checkpoint_id"]),
            "session_id": str(row["session_id"]),
            "preparation_job_id": str(row["prepare_job_id"]),
            "application_id": str(row["application_id"]),
            "provider": str(row["provider"]),
            "checkpoint_kind": str(row["checkpoint_kind"]),
            "status": str(row["status"]),
            "effective_state": (
                WAITING_FOR_USER_AUTH
                if str(row["status"]) == WAITING_FOR_USER_AUTH
                else str(row["status"])
            ),
            "origin": str(row["origin"]),
            "path_sha256": str(row["path_sha256"]),
            "page_fingerprint_sha256": str(row["page_fingerprint_sha256"]),
            "observed_at": str(row["observed_at"]),
            "updated_at": str(row["updated_at"]),
        }

    @staticmethod
    def _job_locked(
        connection: Any,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """SELECT
                   j.job_id,j.session_id,j.tenant_id,j.user_id,j.application_id,
                   j.plan_id,j.provider,j.state AS job_state,j.cancel_requested_at,
                   s.state AS session_state,s.state_version,
                   p.tenant_id AS plan_tenant_id,p.user_id AS plan_user_id
               FROM complete_application_prepare_jobs AS j
               JOIN complete_application_sessions AS s
                 ON s.session_id=j.session_id
               JOIN career_os_application_plans AS p
                 ON p.plan_id=j.plan_id
               WHERE j.job_id=? AND j.tenant_id=? AND j.user_id=?""",
            (job_id, tenant_id, user_id),
        ).fetchone()
        if row is None:
            raise LookupError("Preparation job was not found for this owner")
        result = dict(row)
        if (
            str(result["tenant_id"]) != str(result["plan_tenant_id"])
            or str(result["user_id"]) != str(result["plan_user_id"])
        ):
            raise PermissionError("Preparation job owner binding is invalid")
        return result

    @staticmethod
    def _checkpoint_locked(
        connection: Any,
        *,
        trust_checkpoint_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """SELECT c.*
               FROM complete_application_trust_checkpoints AS c
               JOIN career_os_application_plans AS p ON p.plan_id=c.plan_id
               WHERE c.trust_checkpoint_id=?
                 AND c.tenant_id=? AND c.user_id=?
                 AND p.tenant_id=c.tenant_id AND p.user_id=c.user_id""",
            (trust_checkpoint_id, tenant_id, user_id),
        ).fetchone()
        if row is None:
            raise LookupError("Trust checkpoint was not found for this owner")
        return dict(row)

    @staticmethod
    def _append_event_locked(
        connection: Any,
        *,
        checkpoint_id: str,
        event_type: str,
        evidence: dict[str, Any],
        occurred_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO complete_application_trust_checkpoint_events(
                   event_id,trust_checkpoint_id,event_type,evidence_json,occurred_at
               ) VALUES (?,?,?,?,?)""",
            (
                _event_id(),
                checkpoint_id,
                event_type,
                json.dumps(evidence, sort_keys=True, separators=(",", ":")),
                occurred_at,
            ),
        )

    def observe(
        self,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
        checkpoint_kind: Any,
        current_url: str,
        page_fingerprint: str,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        kind = self._normalize_kind(checkpoint_kind)
        origin, path_sha256 = _safe_location(current_url)
        fingerprint_sha256 = _sha_text(str(page_fingerprint or "unknown"))
        timestamp = observed_at or _now()

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = self._job_locked(
                connection,
                job_id=job_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            active = connection.execute(
                """SELECT * FROM complete_application_trust_checkpoints
                   WHERE session_id=? AND status='WAITING_FOR_USER_AUTH'""",
                (job["session_id"],),
            ).fetchone()
            if active is not None:
                current = dict(active)
                same = (
                    str(current["checkpoint_kind"]) == kind
                    and str(current["origin"]) == origin
                    and str(current["path_sha256"]) == path_sha256
                    and str(current["page_fingerprint_sha256"]) == fingerprint_sha256
                )
                if same:
                    return current
                connection.execute(
                    """UPDATE complete_application_trust_checkpoints
                       SET status='INVALIDATED',invalidated_at=?,updated_at=?
                       WHERE trust_checkpoint_id=?
                         AND status='WAITING_FOR_USER_AUTH'""",
                    (timestamp, timestamp, current["trust_checkpoint_id"]),
                )
                self._append_event_locked(
                    connection,
                    checkpoint_id=str(current["trust_checkpoint_id"]),
                    event_type="INVALIDATED",
                    evidence={"reason": "security_checkpoint_changed"},
                    occurred_at=timestamp,
                )

            checkpoint_id = f"trust-checkpoint-{uuid4()}"
            connection.execute(
                """INSERT INTO complete_application_trust_checkpoints(
                       trust_checkpoint_id,session_id,prepare_job_id,application_id,
                       plan_id,tenant_id,user_id,provider,checkpoint_kind,status,
                       origin,path_sha256,page_fingerprint_sha256,observed_at,
                       updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,'WAITING_FOR_USER_AUTH',?,?,?,?,?)""",
                (
                    checkpoint_id,
                    job["session_id"],
                    job["job_id"],
                    job["application_id"],
                    job["plan_id"],
                    tenant_id,
                    user_id,
                    job["provider"],
                    kind,
                    origin,
                    path_sha256,
                    fingerprint_sha256,
                    timestamp,
                    timestamp,
                ),
            )
            self._append_event_locked(
                connection,
                checkpoint_id=checkpoint_id,
                event_type="OBSERVED",
                evidence={
                    "checkpoint_kind": kind,
                    "origin": origin,
                    "path_sha256": path_sha256,
                    "page_fingerprint_sha256": fingerprint_sha256,
                    "raw_url_persisted": False,
                    "browser_secrets_persisted": False,
                },
                occurred_at=timestamp,
            )
            row = connection.execute(
                """SELECT * FROM complete_application_trust_checkpoints
                   WHERE trust_checkpoint_id=?""",
                (checkpoint_id,),
            ).fetchone()
            assert row is not None
            return dict(row)

    def active_for_job(
        self,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            self._job_locked(
                connection,
                job_id=job_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            row = connection.execute(
                """SELECT * FROM complete_application_trust_checkpoints
                   WHERE prepare_job_id=? AND tenant_id=? AND user_id=?
                     AND status='WAITING_FOR_USER_AUTH'
                   ORDER BY observed_at DESC
                   LIMIT 1""",
                (job_id, tenant_id, user_id),
            ).fetchone()
        return None if row is None else dict(row)

    def active_wire_for_job(
        self,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        return self._wire(
            self.active_for_job(
                job_id=job_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        )

    def decorate_preparation_job(
        self,
        job: dict[str, Any],
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        result = dict(job)
        active = self.active_wire_for_job(
            job_id=str(result["job_id"]),
            tenant_id=tenant_id,
            user_id=user_id,
        )
        result["effective_state"] = (
            WAITING_FOR_USER_AUTH if active is not None else result["state"]
        )
        result["trust_checkpoint"] = active
        return result

    def record_waiting_for_user_auth(
        self,
        *,
        trust_checkpoint_id: str,
        tenant_id: str,
        user_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        """Record a wait without mutating the authoritative session/application state.

        The hosted runner will subsequently translate its local service result to
        the existing non-claimable WAITING_INPUT queue backing state. The sidecar
        effective state remains WAITING_FOR_USER_AUTH.
        """
        timestamp = now or _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            checkpoint = self._checkpoint_locked(
                connection,
                trust_checkpoint_id=trust_checkpoint_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if str(checkpoint["status"]) != WAITING_FOR_USER_AUTH:
                raise ValueError("Trust checkpoint is not active")
            job = self._job_locked(
                connection,
                job_id=str(checkpoint["prepare_job_id"]),
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if str(job["session_state"]) not in _PAUSABLE_SESSION_STATES:
                raise ValueError("Execution session cannot enter user-auth wait")
            if str(job["job_state"]) not in _WAITABLE_JOB_STATES:
                raise ValueError("Preparation job cannot enter user-auth wait")
            if job["cancel_requested_at"] is not None:
                raise ValueError("Cancelled preparation cannot enter user-auth wait")

            prior = connection.execute(
                """SELECT 1 FROM complete_application_trust_checkpoint_events
                   WHERE trust_checkpoint_id=? AND event_type='WAITING_RECORDED'
                   LIMIT 1""",
                (trust_checkpoint_id,),
            ).fetchone()
            if prior is None:
                self._append_event_locked(
                    connection,
                    checkpoint_id=trust_checkpoint_id,
                    event_type="WAITING_RECORDED",
                    evidence={
                        "effective_state": WAITING_FOR_USER_AUTH,
                        "queue_backing_state": "WAITING_INPUT",
                        "session_state_preserved": str(job["session_state"]),
                        "raw_url_persisted": False,
                        "browser_secrets_persisted": False,
                    },
                    occurred_at=timestamp,
                )
            return checkpoint

    def clear_after_verified_user_auth(
        self,
        *,
        trust_checkpoint_id: str,
        tenant_id: str,
        user_id: str,
        current_url: str,
        page_fingerprint: str,
        security_checkpoint_absent: bool,
        now: str | None = None,
    ) -> dict[str, Any]:
        """Clear one verified trust wait and requeue exactly its preparation job.

        Callers must first re-observe the owner-controlled browser and prove the
        security checkpoint is absent. This method persists only safe location
        hashes and never the raw browser state or authentication material.
        """
        if security_checkpoint_absent is not True:
            raise ValueError("User-auth checkpoint cannot clear while security remains active")
        cleared_origin, cleared_path_sha256 = _safe_location(current_url)
        cleared_fingerprint_sha256 = _sha_text(str(page_fingerprint or "unknown"))
        timestamp = now or _now()

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            checkpoint = self._checkpoint_locked(
                connection,
                trust_checkpoint_id=trust_checkpoint_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if str(checkpoint["status"]) == "CLEARED":
                return dict(checkpoint)
            if str(checkpoint["status"]) != WAITING_FOR_USER_AUTH:
                raise ValueError("Only an active trust checkpoint can be cleared")
            job = self._job_locked(
                connection,
                job_id=str(checkpoint["prepare_job_id"]),
                tenant_id=tenant_id,
                user_id=user_id,
            )
            if str(job["job_state"]) != "WAITING_INPUT":
                raise ValueError("Preparation job is not parked for user authentication")
            if job["cancel_requested_at"] is not None:
                raise ValueError("Cancelled preparation cannot be resumed")
            if str(job["session_state"]) not in _PAUSABLE_SESSION_STATES:
                raise ValueError("Execution session is no longer safely resumable")

            updated = connection.execute(
                """UPDATE complete_application_trust_checkpoints
                   SET status='CLEARED',cleared_at=?,updated_at=?
                   WHERE trust_checkpoint_id=? AND status='WAITING_FOR_USER_AUTH'""",
                (timestamp, timestamp, trust_checkpoint_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Trust checkpoint changed while clearing")
            requeued = connection.execute(
                """UPDATE complete_application_prepare_jobs
                   SET state='QUEUED',available_at=?,last_error=NULL,
                       finished_at=NULL,updated_at=?
                   WHERE job_id=? AND state='WAITING_INPUT'
                     AND cancel_requested_at IS NULL""",
                (timestamp, timestamp, checkpoint["prepare_job_id"]),
            )
            if requeued.rowcount != 1:
                raise RuntimeError("Preparation job changed while resuming user-auth wait")
            self._append_event_locked(
                connection,
                checkpoint_id=trust_checkpoint_id,
                event_type="CLEARED",
                evidence={
                    "security_checkpoint_absent": True,
                    "cleared_origin": cleared_origin,
                    "cleared_path_sha256": cleared_path_sha256,
                    "cleared_page_fingerprint_sha256": cleared_fingerprint_sha256,
                    "job_requeued": True,
                    "raw_url_persisted": False,
                    "browser_secrets_persisted": False,
                },
                occurred_at=timestamp,
            )
            refreshed = connection.execute(
                """SELECT * FROM complete_application_trust_checkpoints
                   WHERE trust_checkpoint_id=?""",
                (trust_checkpoint_id,),
            ).fetchone()
            assert refreshed is not None
            return dict(refreshed)
