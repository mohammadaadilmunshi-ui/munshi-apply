"""Durable, non-secret trust checkpoints for browser security boundaries.

This store never persists credentials, cookies, OTP/MFA values, browser storage,
query strings, URL fragments, or page text. It records only enough metadata to
pause cloud execution safely and hand the job to an owner-controlled browser.
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
_BLOCKABLE_SESSION_STATES = frozenset(
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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_location(url: str) -> tuple[str, str]:
    """Return origin + path digest; deliberately discard query and fragment."""
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
    path = parsed.path or "/"
    return origin, _sha_text(path)


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
            "effective_state": WAITING_FOR_USER_AUTH
            if str(row["status"]) == WAITING_FOR_USER_AUTH
            else str(row["status"]),
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
                   j.plan_id,j.provider,j.state AS job_state,
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
        result["effective_state"] = WAITING_FOR_USER_AUTH if active is not None else result["state"]
        result["trust_checkpoint"] = active
        return result

    def block_session_for_user_auth(
        self,
        *,
        trust_checkpoint_id: str,
        tenant_id: str,
        user_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        """Fail closed into BLOCKED while exposing WAITING_FOR_USER_AUTH via sidecar state."""
        timestamp = now or _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT
                       c.*,s.state AS session_state,s.state_version,
                       p.tenant_id AS plan_tenant_id,p.user_id AS plan_user_id
                   FROM complete_application_trust_checkpoints AS c
                   JOIN complete_application_sessions AS s
                     ON s.session_id=c.session_id
                   JOIN career_os_application_plans AS p
                     ON p.plan_id=c.plan_id
                   WHERE c.trust_checkpoint_id=?
                     AND c.tenant_id=? AND c.user_id=?
                     AND c.status='WAITING_FOR_USER_AUTH'""",
                (trust_checkpoint_id, tenant_id, user_id),
            ).fetchone()
            if row is None:
                raise LookupError("Active trust checkpoint was not found for this owner")
            checkpoint = dict(row)
            if (
                str(checkpoint["tenant_id"]) != str(checkpoint["plan_tenant_id"])
                or str(checkpoint["user_id"]) != str(checkpoint["plan_user_id"])
            ):
                raise PermissionError("Trust checkpoint owner binding is invalid")

            state = str(checkpoint["session_state"])
            if state != "BLOCKED":
                if state not in _BLOCKABLE_SESSION_STATES:
                    raise ValueError(
                        "Execution session cannot enter user-auth wait from this state"
                    )
                updated = connection.execute(
                    """UPDATE complete_application_sessions
                       SET state='BLOCKED',state_version=state_version+1,updated_at=?
                       WHERE session_id=? AND state=?""",
                    (timestamp, checkpoint["session_id"], state),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("Execution session changed while entering user-auth wait")
                application_updated = connection.execute(
                    """UPDATE applications
                       SET status='BLOCKED',updated_at=?
                       WHERE application_id=?""",
                    (timestamp, checkpoint["application_id"]),
                )
                if application_updated.rowcount != 1:
                    raise RuntimeError("Apply application changed while entering user-auth wait")
                self._append_event_locked(
                    connection,
                    checkpoint_id=trust_checkpoint_id,
                    event_type="SESSION_BLOCKED",
                    evidence={
                        "effective_state": WAITING_FOR_USER_AUTH,
                        "checkpoint_kind": checkpoint["checkpoint_kind"],
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
