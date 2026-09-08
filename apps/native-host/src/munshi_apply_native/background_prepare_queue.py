"""Durable background-preparation queue for the MUNSHI Apply execution plane.

This module owns only pre-submission preparation work. It deliberately does
not create reviews, grant submission authority, click final-submit controls,
verify submissions, write receipts, or send mail.

The queue makes Apply's existing CompleteApplicationLoopService.prepare_session
restart-safe by adding durable enqueue/idempotency, atomic worker claim,
worker ownership + lease, heartbeat, cooperative cancellation, expired-lease
recovery, bounded pre-submit retry, and WAITING_INPUT -> QUEUED resumption.

A later hosted-browser tranche supplies the concrete PlanBrowserAdapter factory.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from .database import Database

PREPARE_JOB_STATES = frozenset(
    {
        "QUEUED",
        "RUNNING",
        "WAITING_INPUT",
        "READY_FOR_REVIEW",
        "BLOCKED",
        "FAILED_SAFELY",
        "CANCELLED",
    }
)

TERMINAL_PREPARE_JOB_STATES = frozenset(
    {"READY_FOR_REVIEW", "BLOCKED", "FAILED_SAFELY", "CANCELLED"}
)

PREPARABLE_SESSION_STATES = frozenset(
    {
        "SESSION_STARTING",
        "JOB_VERIFIED",
        "FORM_DISCOVERED",
        "PREPARING",
        "NEEDS_INPUT",
        "READY_FOR_REVIEW",
    }
)

_SESSION_TO_JOB_STATE = {
    "NEEDS_INPUT": "WAITING_INPUT",
    "READY_FOR_REVIEW": "READY_FOR_REVIEW",
    "BLOCKED": "BLOCKED",
    "FAILED_SAFELY": "FAILED_SAFELY",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lease_until(now: str, seconds: int) -> str:
    if seconds < 1:
        raise ValueError("Lease seconds must be positive")
    parsed = datetime.fromisoformat(now)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (parsed + timedelta(seconds=seconds)).astimezone(UTC).isoformat()


def _clean_error(error: BaseException) -> str:
    text = " ".join(str(error).split())
    return (text or error.__class__.__name__)[:1000]


@dataclass(frozen=True)
class PreparationRunResult:
    job_id: str
    session_id: str
    job_state: str
    session_state: str | None
    attempt_count: int
    retry_scheduled: bool


class PreparationService(Protocol):
    def prepare_session(self, *, session_id: str, adapter: Any) -> Any: ...


class DurablePreparationQueue:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _owned_session(
        self,
        *,
        session_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT
                       s.session_id,s.application_id,s.plan_id,s.provider,s.state,
                       p.tenant_id,p.user_id
                   FROM complete_application_sessions AS s
                   JOIN career_os_application_plans AS p ON p.plan_id=s.plan_id
                   WHERE s.session_id=?""",
                (session_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Preparation session was not found")
        result = dict(row)
        if result["tenant_id"] != tenant_id or result["user_id"] != user_id:
            raise PermissionError("Preparation session belongs to another owner")
        return result

    def enqueue_session(
        self,
        *,
        session_id: str,
        tenant_id: str,
        user_id: str,
        max_attempts: int = 3,
        now: str | None = None,
    ) -> dict[str, Any]:
        if max_attempts < 1 or max_attempts > 10:
            raise ValueError("Preparation max_attempts must be between 1 and 10")
        session = self._owned_session(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if str(session["state"]) not in PREPARABLE_SESSION_STATES:
            raise ValueError("Execution session is not eligible for background preparation")
        timestamp = now or _now()

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE session_id=?""",
                (session_id,),
            ).fetchone()
            if existing is not None:
                result = dict(existing)
                if result["tenant_id"] != tenant_id or result["user_id"] != user_id:
                    raise PermissionError("Preparation job belongs to another owner")
                return result

            job_id = f"prepare-job-{uuid4()}"
            connection.execute(
                """INSERT INTO complete_application_prepare_jobs(
                       job_id,session_id,tenant_id,user_id,application_id,plan_id,
                       provider,state,attempt_count,max_attempts,available_at,
                       created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,'QUEUED',0,?,?,?,?)""",
                (
                    job_id,
                    session_id,
                    tenant_id,
                    user_id,
                    session["application_id"],
                    session["plan_id"],
                    session["provider"],
                    max_attempts,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM complete_application_prepare_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            assert row is not None
            return dict(row)

    def get(
        self,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE job_id=? AND tenant_id=? AND user_id=?""",
                (job_id, tenant_id, user_id),
            ).fetchone()
        if row is None:
            raise LookupError("Preparation job was not found for this owner")
        return dict(row)

    def get_for_session(
        self,
        *,
        session_id: str,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE session_id=? AND tenant_id=? AND user_id=?""",
                (session_id, tenant_id, user_id),
            ).fetchone()
        return None if row is None else dict(row)

    @staticmethod
    def _recover_expired_locked(connection: Any, timestamp: str) -> int:
        cancelled = connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='CANCELLED',lease_owner=NULL,lease_expires_at=NULL,
                   heartbeat_at=NULL,finished_at=COALESCE(finished_at,?),
                   updated_at=?
               WHERE state='RUNNING' AND lease_expires_at IS NOT NULL
                 AND lease_expires_at<=? AND cancel_requested_at IS NOT NULL""",
            (timestamp, timestamp, timestamp),
        ).rowcount
        exhausted = connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='FAILED_SAFELY',lease_owner=NULL,lease_expires_at=NULL,
                   heartbeat_at=NULL,finished_at=COALESCE(finished_at,?),
                   last_error='Expired pre-submit worker lease exhausted retry budget',
                   updated_at=?
               WHERE state='RUNNING' AND lease_expires_at IS NOT NULL
                 AND lease_expires_at<=? AND cancel_requested_at IS NULL
                 AND attempt_count>=max_attempts""",
            (timestamp, timestamp, timestamp),
        ).rowcount
        recovered = connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='QUEUED',lease_owner=NULL,lease_expires_at=NULL,
                   heartbeat_at=NULL,available_at=?,
                   last_error='Recovered expired pre-submit worker lease',
                   updated_at=?
               WHERE state='RUNNING' AND lease_expires_at IS NOT NULL
                 AND lease_expires_at<=? AND cancel_requested_at IS NULL
                 AND attempt_count<max_attempts""",
            (timestamp, timestamp, timestamp),
        ).rowcount
        return int(cancelled + exhausted + recovered)

    def recover_expired_leases(self, *, now: str | None = None) -> int:
        timestamp = now or _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._recover_expired_locked(connection, timestamp)

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        now: str | None = None,
    ) -> dict[str, Any] | None:
        worker = " ".join(str(worker_id or "").split())
        if not worker:
            raise ValueError("Worker id is required")
        timestamp = now or _now()
        lease_expires = _lease_until(timestamp, lease_seconds)

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_expired_locked(connection, timestamp)
            row = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE state='QUEUED'
                     AND cancel_requested_at IS NULL
                     AND available_at<=?
                     AND attempt_count<max_attempts
                   ORDER BY created_at,job_id
                   LIMIT 1""",
                (timestamp,),
            ).fetchone()
            if row is None:
                return None
            job_id = str(row["job_id"])
            updated = connection.execute(
                """UPDATE complete_application_prepare_jobs
                   SET state='RUNNING',attempt_count=attempt_count+1,
                       lease_owner=?,lease_expires_at=?,heartbeat_at=?,updated_at=?
                   WHERE job_id=? AND state='QUEUED'
                     AND cancel_requested_at IS NULL
                     AND attempt_count<max_attempts""",
                (worker, lease_expires, timestamp, timestamp, job_id),
            )
            if updated.rowcount != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM complete_application_prepare_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            assert claimed is not None
            return dict(claimed)

    def heartbeat(
        self,
        *,
        job_id: str,
        worker_id: str,
        lease_seconds: int = 300,
        now: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now or _now()
        lease_expires = _lease_until(timestamp, lease_seconds)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """UPDATE complete_application_prepare_jobs
                   SET heartbeat_at=?,lease_expires_at=?,updated_at=?
                   WHERE job_id=? AND state='RUNNING' AND lease_owner=?""",
                (timestamp, lease_expires, timestamp, job_id, worker_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Preparation lease is not owned by this worker")
            row = connection.execute(
                "SELECT * FROM complete_application_prepare_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            assert row is not None
            return dict(row)

    def request_cancel(
        self,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now or _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE job_id=? AND tenant_id=? AND user_id=?""",
                (job_id, tenant_id, user_id),
            ).fetchone()
            if row is None:
                raise LookupError("Preparation job was not found for this owner")
            current = str(row["state"])
            if current in TERMINAL_PREPARE_JOB_STATES:
                return dict(row)
            if current in {"QUEUED", "WAITING_INPUT"}:
                connection.execute(
                    """UPDATE complete_application_prepare_jobs
                       SET state='CANCELLED',cancel_requested_at=?,
                           finished_at=COALESCE(finished_at,?),updated_at=?
                       WHERE job_id=?""",
                    (timestamp, timestamp, timestamp, job_id),
                )
            elif current == "RUNNING":
                connection.execute(
                    """UPDATE complete_application_prepare_jobs
                       SET cancel_requested_at=?,updated_at=?
                       WHERE job_id=?""",
                    (timestamp, timestamp, job_id),
                )
            else:
                raise ValueError("Preparation job cannot be cancelled from its current state")
            updated = connection.execute(
                "SELECT * FROM complete_application_prepare_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            assert updated is not None
            return dict(updated)

    def finish(
        self,
        *,
        job_id: str,
        worker_id: str,
        session_state: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now or _now()
        target = _SESSION_TO_JOB_STATE.get(str(session_state))
        if target is None:
            raise ValueError("Worker returned a non-terminal preparation state")

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE job_id=? AND state='RUNNING' AND lease_owner=?""",
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("Preparation lease is not owned by this worker")
            if row["cancel_requested_at"] is not None:
                target = "CANCELLED"
            finished_at = timestamp if target in TERMINAL_PREPARE_JOB_STATES else None
            connection.execute(
                """UPDATE complete_application_prepare_jobs
                   SET state=?,lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,
                       finished_at=?,updated_at=?
                   WHERE job_id=? AND state='RUNNING' AND lease_owner=?""",
                (target, finished_at, timestamp, job_id, worker_id),
            )
            updated = connection.execute(
                "SELECT * FROM complete_application_prepare_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            assert updated is not None
            return dict(updated)

    def fail(
        self,
        *,
        job_id: str,
        worker_id: str,
        error: BaseException,
        retryable: bool,
        now: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now or _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE job_id=? AND state='RUNNING' AND lease_owner=?""",
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("Preparation lease is not owned by this worker")

            cancelled = row["cancel_requested_at"] is not None
            attempts = int(row["attempt_count"])
            maximum = int(row["max_attempts"])
            if cancelled:
                target = "CANCELLED"
            elif retryable and attempts < maximum:
                target = "QUEUED"
            else:
                target = "FAILED_SAFELY"
            finished_at = timestamp if target in TERMINAL_PREPARE_JOB_STATES else None
            connection.execute(
                """UPDATE complete_application_prepare_jobs
                   SET state=?,lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,
                       available_at=?,last_error=?,finished_at=?,updated_at=?
                   WHERE job_id=? AND state='RUNNING' AND lease_owner=?""",
                (
                    target,
                    timestamp,
                    _clean_error(error),
                    finished_at,
                    timestamp,
                    job_id,
                    worker_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM complete_application_prepare_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            assert updated is not None
            return dict(updated)

    def requeue_session(
        self,
        *,
        session_id: str,
        tenant_id: str,
        user_id: str,
        now: str | None = None,
    ) -> dict[str, Any] | None:
        timestamp = now or _now()
        self._owned_session(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM complete_application_prepare_jobs
                   WHERE session_id=? AND tenant_id=? AND user_id=?""",
                (session_id, tenant_id, user_id),
            ).fetchone()
            if row is None:
                return None
            if str(row["state"]) == "WAITING_INPUT":
                connection.execute(
                    """UPDATE complete_application_prepare_jobs
                       SET state='QUEUED',available_at=?,last_error=NULL,
                           finished_at=NULL,updated_at=?
                       WHERE job_id=? AND state='WAITING_INPUT'
                         AND cancel_requested_at IS NULL""",
                    (timestamp, timestamp, row["job_id"]),
                )
            updated = connection.execute(
                "SELECT * FROM complete_application_prepare_jobs WHERE job_id=?",
                (row["job_id"],),
            ).fetchone()
            assert updated is not None
            return dict(updated)


class DurablePreparationWorker:
    """One-claim-at-a-time worker that can only call prepare_session."""

    def __init__(
        self,
        queue: DurablePreparationQueue,
        *,
        service_factory: Callable[[dict[str, Any]], PreparationService],
        adapter_factory: Callable[[dict[str, Any]], Any],
        lease_seconds: int = 300,
    ) -> None:
        self.queue = queue
        self.service_factory = service_factory
        self.adapter_factory = adapter_factory
        self.lease_seconds = lease_seconds

    def run_once(
        self,
        *,
        worker_id: str,
        now: str | None = None,
    ) -> PreparationRunResult | None:
        job = self.queue.claim_next(
            worker_id=worker_id,
            lease_seconds=self.lease_seconds,
            now=now,
        )
        if job is None:
            return None

        try:
            service = self.service_factory(job)
            adapter = self.adapter_factory(job)
            result = service.prepare_session(
                session_id=str(job["session_id"]),
                adapter=adapter,
            )
            session_state = str(result.state)
            finished = self.queue.finish(
                job_id=str(job["job_id"]),
                worker_id=worker_id,
                session_state=session_state,
                now=now,
            )
            return PreparationRunResult(
                job_id=str(finished["job_id"]),
                session_id=str(finished["session_id"]),
                job_state=str(finished["state"]),
                session_state=session_state,
                attempt_count=int(finished["attempt_count"]),
                retry_scheduled=False,
            )
        except (LookupError, PermissionError, RuntimeError, ValueError) as error:
            failed = self.queue.fail(
                job_id=str(job["job_id"]),
                worker_id=worker_id,
                error=error,
                retryable=False,
                now=now,
            )
            return PreparationRunResult(
                job_id=str(failed["job_id"]),
                session_id=str(failed["session_id"]),
                job_state=str(failed["state"]),
                session_state=None,
                attempt_count=int(failed["attempt_count"]),
                retry_scheduled=False,
            )
        except Exception as error:
            failed = self.queue.fail(
                job_id=str(job["job_id"]),
                worker_id=worker_id,
                error=error,
                retryable=True,
                now=now,
            )
            return PreparationRunResult(
                job_id=str(failed["job_id"]),
                session_id=str(failed["session_id"]),
                job_state=str(failed["state"]),
                session_state=None,
                attempt_count=int(failed["attempt_count"]),
                retry_scheduled=str(failed["state"]) == "QUEUED",
            )
