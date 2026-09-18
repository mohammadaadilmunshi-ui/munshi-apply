"""Canonical hosted final-submit worker for the single-approval Complete Loop.

This worker is deliberately separate from background preparation. It is the
only hosted runtime allowed to turn Hunter's already-issued one-use authority
into Apply's internal READY_TO_SUBMIT marker and then call the guarded
``CompleteApplicationLoopService.submit`` boundary.

No customer-facing approval is created here. Hunter's authenticated
SUBMIT_AUTHORIZATION_READ proves that the one visible Approve & Submit action
already happened; Hunter's atomic CLAIM remains the one-use authority boundary.
All production switches are default-off and the existing submit service still
re-checks them immediately before the employer action.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .background_prepare_queue import DurablePreparationQueue
from .complete_application_loop import (
    FINAL_REVIEW_ENV,
    FINAL_SUBMIT_ENV,
    PRODUCTION_AUTHORITY_ENV,
    CompleteApplicationLoopService,
)
from .database import Database
from .hosted_prepare_worker import (
    BRIDGE_URL_ENV,
    NORMAL_AUTOFILL_ENV,
    RESUME_UPLOAD_ENV,
    HostedAdapterFactory,
)
from .hunter_submit_authority_client_v1 import (
    HunterSubmitAuthorityClient,
    SubmitAuthorizationClientError,
)
from .settings import Settings
from .submit_authority_inbox_v1 import SubmitAuthorityInbox

HOSTED_SUBMIT_WORKER_ENV = "MUNSHI_APPLY_HOSTED_SUBMIT_WORKER_ENABLED"
POLL_SECONDS_ENV = "MUNSHI_APPLY_SUBMIT_POLL_SECONDS"


def _truthy(name: str) -> bool:
    return str(os.getenv(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_submit_key(authorization_id: str, review_id: str) -> str:
    digest = hashlib.sha256(f"{authorization_id}\0{review_id}".encode()).hexdigest()
    return "canonical-submit-" + digest[:40]


@dataclass(frozen=True)
class HostedSubmitRunResult:
    session_id: str
    application_id: str
    state: str
    attempted: bool
    verification_status: str | None = None
    error: str | None = None


class HostedSubmitRunner:
    """Poll durable single-approval submissions and retry receipt handoff safely."""

    def __init__(
        self,
        database: Database,
        *,
        adapter_factory: Any,
        authority_client: HunterSubmitAuthorityClient,
        production_receipt_client: Any | None = None,
        candidate_limit: int = 50,
    ) -> None:
        self.database = database
        self.queue = DurablePreparationQueue(database)
        self.adapter_factory = adapter_factory
        self.authority_client = authority_client
        self.production_receipt_client = production_receipt_client
        self.candidate_limit = max(1, min(int(candidate_limit), 250))

    def _candidates(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT s.session_id,s.application_id,s.plan_id,s.provider,s.state,
                          s.browser_form_digest,s.checkpoint_id,s.current_url,
                          p.tenant_id,p.user_id,p.plan_digest
                   FROM complete_application_sessions AS s
                   JOIN career_os_application_plans AS p ON p.plan_id=s.plan_id
                   WHERE s.state IN ('READY_TO_SUBMIT','READY_FOR_REVIEW')
                     AND NOT EXISTS (
                       SELECT 1 FROM final_submit_commands AS c
                       WHERE c.session_id=s.session_id
                     )
                   ORDER BY CASE s.state WHEN 'READY_TO_SUBMIT' THEN 0 ELSE 1 END,
                            s.updated_at,s.session_id
                   LIMIT ?""",
                (self.candidate_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _local_review(self, session: Mapping[str, Any]) -> dict[str, Any]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM final_application_reviews
                   WHERE session_id=? AND application_id=? AND plan_id=?
                     AND invalidated_at IS NULL
                   ORDER BY created_at DESC,review_id DESC LIMIT 2""",
                (
                    session["session_id"],
                    session["application_id"],
                    session["plan_id"],
                ),
            ).fetchall()
        if not rows:
            raise LookupError("No current local frozen review exists for the session")
        if len(rows) > 1 and str(rows[0]["review_digest"]) != str(rows[1]["review_digest"]):
            raise RuntimeError("Multiple current local review snapshots exist for the session")
        return dict(rows[0])

    @staticmethod
    def _assert_authority_matches_local_review(
        *,
        envelope: Mapping[str, Any],
        session: Mapping[str, Any],
        review: Mapping[str, Any],
        plan_record: Mapping[str, Any],
    ) -> None:
        plan = dict(plan_record["plan"])
        snapshot = json.loads(str(review["review_json"]))
        if not isinstance(snapshot, dict):
            raise ValueError("Local frozen review snapshot is malformed")
        cover = snapshot.get("cover_letter")
        expected_cover = (
            str(cover.get("sha256") or "") if isinstance(cover, dict) else None
        )
        exact = {
            "tenant_id": session["tenant_id"],
            "user_id": session["user_id"],
            "application_id": session["application_id"],
            "plan_id": session["plan_id"],
            "session_id": session["session_id"],
            "provider": str(session["provider"]).upper(),
            "target_url": str(snapshot.get("destination_url") or ""),
            "checkpoint_id": str(snapshot.get("checkpoint_id") or ""),
            "plan_digest": review["plan_digest"],
            "browser_form_digest": review["browser_form_digest"],
            "resume_sha256": review["resume_digest"],
        }
        for key, expected in exact.items():
            actual = envelope.get(key)
            if key == "provider":
                actual = str(actual or "").upper()
            if str(actual or "") != str(expected or ""):
                raise PermissionError(f"Canonical authority/local review mismatch: {key}")
        if envelope.get("cover_letter_sha256") != expected_cover:
            raise PermissionError("Canonical authority/local review mismatch: cover letter")
        if str(plan_record["plan_digest"]) != str(review["plan_digest"]):
            raise ValueError("Local Application Plan changed after review")
        if str(plan["resume"]["artifact_sha256"]) != str(review["resume_digest"]):
            raise ValueError("Local resume changed after review")
        if str(session.get("browser_form_digest") or "") != str(review["browser_form_digest"]):
            raise ValueError("Local browser form changed after review")
        if str(session.get("checkpoint_id") or "") != str(snapshot.get("checkpoint_id") or ""):
            raise ValueError("Local checkpoint changed after review")
        if str(session.get("current_url") or "") != str(snapshot.get("destination_url") or ""):
            raise ValueError("Local destination changed after review")

    def _read_authority(
        self,
        *,
        session: Mapping[str, Any],
        plan_record: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.authority_client.read(
            {
                "tenant_id": session["tenant_id"],
                "user_id": session["user_id"],
                "application_id": session["application_id"],
                "plan_id": session["plan_id"],
                "session_id": session["session_id"],
                "plan_digest": plan_record["plan_digest"],
            }
        )

    def _claim_authority(
        self,
        *,
        inbox: SubmitAuthorityInbox,
        envelope: Mapping[str, Any],
    ) -> None:
        phase = inbox.claim_for_execution(
            authorization_id=str(envelope["authorization_id"]),
            now=_now(),
        )
        if phase.claimed and phase.state == "CLAIMED" and phase.claim_digest:
            return
        if not phase.claimed or phase.state != "CLAIM_IN_FLIGHT" or not phase.claimant_id:
            raise RuntimeError(f"Canonical submit authority claim cannot start: {phase.error}")
        claim = self.authority_client.claim(envelope, claimant_id=phase.claimant_id)
        finalized = inbox.finalize_claim(
            authorization_id=str(envelope["authorization_id"]),
            claim_digest=str(claim["claim_digest"]),
            now=_now(),
        )
        if not finalized.claimed or finalized.state != "CLAIMED":
            raise RuntimeError(
                f"Canonical submit authority claim could not finalize: {finalized.error}"
            )

    @staticmethod
    def _assert_rebuilt_form(
        *,
        prepared: Mapping[str, Any],
        review: Mapping[str, Any],
        plan_record: Mapping[str, Any],
    ) -> None:
        plan = dict(plan_record["plan"])
        if str(prepared.get("form_digest") or "") != str(review["browser_form_digest"]):
            raise ValueError("Rebuilt browser form does not match the frozen review")
        if prepared.get("resume_uploaded") is not True or str(
            prepared.get("resume_sha256") or ""
        ) != str(review["resume_digest"]):
            raise ValueError("Rebuilt browser resume does not match the frozen review")
        cover = plan.get("cover_letter")
        if isinstance(cover, dict):
            if prepared.get("cover_letter_uploaded") is not True or str(
                prepared.get("cover_letter_sha256") or ""
            ) != str(cover.get("artifact_sha256") or ""):
                raise ValueError("Rebuilt cover letter does not match the frozen review")
        if prepared.get("unresolved") or prepared.get("validation_errors"):
            raise ValueError("Rebuilt browser form is no longer submission-ready")
        if int(prepared.get("completed_required_fields") or 0) < int(
            prepared.get("required_fields") or 0
        ):
            raise ValueError("Rebuilt browser form has incomplete required fields")

    def _retry_pending_receipt(self) -> HostedSubmitRunResult | None:
        """Retry Hunter receipt handoff only; never re-enter the employer boundary."""
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT o.command_id,s.session_id,s.application_id,
                          p.tenant_id,p.user_id
                   FROM production_receipt_outbox AS o
                   JOIN final_submit_commands AS c ON c.command_id=o.command_id
                   JOIN complete_application_sessions AS s ON s.session_id=c.session_id
                   JOIN career_os_application_plans AS p ON p.plan_id=s.plan_id
                   WHERE o.state='PENDING'
                   ORDER BY o.updated_at,o.receipt_id
                   LIMIT 1"""
            ).fetchone()
        if row is None:
            return None

        service = CompleteApplicationLoopService(
            self.database,
            tenant_id=str(row["tenant_id"]),
            user_id=str(row["user_id"]),
            production_receipt_client=self.production_receipt_client,
        )
        delivery = service._deliver_pending_production_receipt(  # noqa: SLF001
            str(row["command_id"])
        )
        if not delivery or str(delivery.get("state")) != "DELIVERED":
            error = None if not delivery else delivery.get("error")
            return HostedSubmitRunResult(
                session_id=str(row["session_id"]),
                application_id=str(row["application_id"]),
                state="RECEIPT_PENDING",
                attempted=False,
                verification_status="VERIFIED",
                error=str(error or "Verified production receipt delivery remains pending"),
            )
        return HostedSubmitRunResult(
            session_id=str(row["session_id"]),
            application_id=str(row["application_id"]),
            state="RECEIPT_DELIVERED",
            attempted=False,
            verification_status="VERIFIED",
        )

    def _run_session(self, session: dict[str, Any]) -> HostedSubmitRunResult:
        service = CompleteApplicationLoopService(
            self.database,
            tenant_id=str(session["tenant_id"]),
            user_id=str(session["user_id"]),
            submit_authority_client=self.authority_client,
            production_receipt_client=self.production_receipt_client,
        )
        plan_record = service._plan(str(session["plan_id"]))  # noqa: SLF001
        review = self._local_review(session)
        inbox = SubmitAuthorityInbox(self.database)
        service.bind_submit_authority_inbox(inbox)

        envelope = inbox.authority_for_session(session_id=str(session["session_id"]))
        if str(session["state"]) == "READY_FOR_REVIEW":
            # A pushed envelope is deliberately not enough to synthesize the
            # local approval marker. Re-read it over Hunter's authenticated
            # control channel, then bind that exact authority to the local
            # frozen review before advancing state.
            envelope = self._read_authority(session=session, plan_record=plan_record)
            self._assert_authority_matches_local_review(
                envelope=envelope,
                session=session,
                review=review,
                plan_record=plan_record,
            )
            service.approve_review(review_id=str(review["review_id"]))
            session = {
                **session,
                **service._session(str(session["session_id"])),  # noqa: SLF001
                "tenant_id": session["tenant_id"],
                "user_id": session["user_id"],
            }
            accepted = inbox.accept(dict(envelope), now=_now())
            if not accepted.accepted:
                raise RuntimeError(
                    f"Authenticated canonical authority was rejected locally: {accepted.error}"
                )
        elif envelope is None:
            envelope = self._read_authority(session=session, plan_record=plan_record)
            self._assert_authority_matches_local_review(
                envelope=envelope,
                session=session,
                review=review,
                plan_record=plan_record,
            )
            accepted = inbox.accept(dict(envelope), now=_now())
            if not accepted.accepted:
                raise RuntimeError(
                    f"Authenticated canonical authority was rejected locally: {accepted.error}"
                )
        else:
            self._assert_authority_matches_local_review(
                envelope=envelope,
                session=session,
                review=review,
                plan_record=plan_record,
            )

        assert envelope is not None
        self._claim_authority(inbox=inbox, envelope=envelope)

        prepare_job = self.queue.get_for_session(
            session_id=str(session["session_id"]),
            tenant_id=str(session["tenant_id"]),
            user_id=str(session["user_id"]),
        )
        if prepare_job is None or str(prepare_job.get("state") or "") != "READY_FOR_REVIEW":
            raise RuntimeError("Canonical submit requires a completed hosted preparation job")

        adapter = self.adapter_factory(prepare_job)
        try:
            plan = dict(plan_record["plan"])
            prepared = adapter.prepare_form(
                plan=plan,
                checkpoint=service.checkpoints.latest(str(session["application_id"])),
                resolved_values=service._resolved_values(  # noqa: SLF001
                    str(session["application_id"]), str(session["session_id"])
                ),
            )
            self._assert_rebuilt_form(
                prepared=prepared,
                review=review,
                plan_record=plan_record,
            )
            receipt = service.submit(
                review_id=str(review["review_id"]),
                idempotency_key=_stable_submit_key(
                    str(envelope["authorization_id"]), str(review["review_id"])
                ),
                adapter=adapter,
            )
        finally:
            close = getattr(adapter, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()

        return HostedSubmitRunResult(
            session_id=str(session["session_id"]),
            application_id=str(session["application_id"]),
            state=str(receipt.get("verification_status") or "UNKNOWN"),
            attempted=True,
            verification_status=str(receipt.get("verification_status") or "") or None,
        )

    def run_once(self) -> HostedSubmitRunResult | None:
        pending_receipt = self._retry_pending_receipt()
        if pending_receipt is not None and pending_receipt.error is None:
            return pending_receipt

        for session in self._candidates():
            try:
                return self._run_session(session)
            except SubmitAuthorizationClientError:
                # No current Hunter authority generally means the candidate has
                # not received the sole customer Approve & Submit action yet.
                # Leave it untouched and inspect the next ready candidate.
                continue
            except (LookupError, PermissionError, RuntimeError, ValueError) as error:
                return HostedSubmitRunResult(
                    session_id=str(session["session_id"]),
                    application_id=str(session["application_id"]),
                    state=str(session["state"]),
                    attempted=False,
                    error=str(error),
                )
        return pending_receipt


def run_forever() -> None:
    required = (
        HOSTED_SUBMIT_WORKER_ENV,
        FINAL_REVIEW_ENV,
        FINAL_SUBMIT_ENV,
        PRODUCTION_AUTHORITY_ENV,
        RESUME_UPLOAD_ENV,
        NORMAL_AUTOFILL_ENV,
    )
    disabled = [name for name in required if not _truthy(name)]
    if disabled:
        raise RuntimeError("Hosted canonical submit worker is disabled: " + ", ".join(disabled))

    settings = Settings.from_environment()
    if not settings.handoff_hmac_secret:
        raise RuntimeError("Apply handoff HMAC secret is required for canonical submit")
    bridge_url = str(
        os.getenv("MUNSHI_HUNTER_BASE_URL") or os.getenv(BRIDGE_URL_ENV) or ""
    ).strip()
    if not bridge_url:
        raise RuntimeError("Hunter execution bridge base URL is required")

    database = Database(settings.database_path, settings.migrations_path)
    database.migrate()
    queue = DurablePreparationQueue(database)
    adapter_factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url=bridge_url,
        bridge_secret=settings.handoff_hmac_secret,
        browser_executable=os.getenv("MUNSHI_BROWSER_EXECUTABLE") or None,
        navigation_timeout_ms=int(os.getenv("MUNSHI_APPLY_BROWSER_TIMEOUT_MS", "30000")),
        # Rebuilding the already-reviewed form must have the same deterministic
        # Teach -> Sonnet recovery stack as preparation. Recovery still has no
        # submit authority; CompleteApplicationLoopService keeps that boundary.
        runtime_root=settings.runtime_root,
    )
    runner = HostedSubmitRunner(
        database,
        adapter_factory=adapter_factory,
        authority_client=HunterSubmitAuthorityClient.from_environment(),
    )
    worker_id = str(
        os.getenv("MUNSHI_APPLY_SUBMIT_WORKER_ID")
        or f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
    )
    poll = max(0.25, min(30.0, float(os.getenv(POLL_SECONDS_ENV, "1"))))
    while True:
        result = runner.run_once()
        if result is not None and result.error:
            # Keep the daemon fail-closed without tight-looping a deterministic
            # pre-submit mismatch. No authority is retried across an employer
            # boundary; CompleteApplicationLoopService owns that guarantee.
            time.sleep(max(poll, 2.0))
        else:
            time.sleep(poll)
        _ = worker_id  # Reserved for structured worker telemetry.


def main() -> int:
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
