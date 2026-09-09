"""Independent synthetic submission verification and immutable receipt authority."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .application_plan_handoff_v2 import _plan_digest_payload, _sha256_json
from .database import Database, canonical_json
from .execution_policy import safe_evidence

SYNTHETIC_VERIFICATION_ENV = "MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED"
VERIFICATION_METHOD = "SYNTHETIC_PROVIDER_LOOKUP"


def _enabled() -> bool:
    return str(os.getenv(SYNTHETIC_VERIFICATION_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Verification timestamp is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Verification timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("Verification timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _event_id(replay_identity: str) -> str:
    return "loop-event-" + hashlib.sha256(replay_identity.encode("utf-8")).hexdigest()[:32]


class SyntheticSubmissionVerifier(Protocol):
    def observe_submission(
        self,
        *,
        plan: dict[str, Any],
        provider_application_id: str,
        target_url: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SyntheticVerificationResult:
    command_id: str
    verified: bool
    state: str
    replayed: bool
    receipt_id: str | None = None
    receipt_digest: str | None = None
    error: str | None = None


class SyntheticSubmissionVerificationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _receipt(self, command_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM synthetic_submission_receipts WHERE command_id=?",
                (command_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def _context(self, command_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            inbox = connection.execute(
                "SELECT * FROM synthetic_submit_command_inbox WHERE command_id=?",
                (command_id,),
            ).fetchone()
            execution = connection.execute(
                "SELECT * FROM synthetic_submit_executions WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if inbox is None or execution is None:
                raise LookupError("Synthetic submit command or execution was not found")
            session = connection.execute(
                "SELECT * FROM complete_application_sessions WHERE session_id=?",
                (execution["session_id"],),
            ).fetchone()
            application = connection.execute(
                "SELECT * FROM applications WHERE application_id=?",
                (execution["application_id"],),
            ).fetchone()
            plan_row = connection.execute(
                """SELECT * FROM career_os_application_plans
                   WHERE plan_id=? AND tenant_id=? AND user_id=?""",
                (execution["plan_id"], inbox["tenant_id"], inbox["user_id"]),
            ).fetchone()

        if session is None or application is None or plan_row is None:
            raise LookupError("Synthetic submission verification context is incomplete")
        if str(execution["state"]) != "SUBMITTED":
            raise ValueError("Only a SUBMITTED synthetic execution may be verified")
        if execution["action_executed"] != 1:
            raise ValueError("Synthetic execution does not prove a submit action occurred")
        if not str(execution["provider_application_id"] or "").strip():
            raise ValueError("Synthetic execution has no provider application identity")
        if not str(execution["completed_at"] or "").strip():
            raise ValueError("Synthetic execution has no submitted timestamp")
        if str(session["state"]) != "SUBMITTED":
            raise ValueError("Execution session is not SUBMITTED")
        if str(application["status"]) != "SUBMITTED":
            raise ValueError("Application is not SUBMITTED")
        if str(execution["provider"]).upper() != str(inbox["provider"]).upper():
            raise ValueError("Synthetic execution provider binding changed")
        for key in ("application_id", "plan_id", "session_id"):
            if str(execution[key]) != str(inbox[key]):
                raise ValueError(f"Synthetic execution {key} binding changed")
        if len(str(execution["result_digest"] or "")) != 64:
            raise ValueError("Synthetic execution result digest is unavailable")

        try:
            plan = json.loads(str(plan_row["plan_json"]))
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("Stored Application Plan is malformed") from error
        if not isinstance(plan, dict):
            raise ValueError("Stored Application Plan is malformed")
        if _sha256_json(_plan_digest_payload(plan)) != str(plan_row["plan_digest"]):
            raise ValueError("Stored Application Plan integrity failure")
        if str(plan_row["plan_digest"]) != str(inbox["plan_digest"]):
            raise ValueError("Application Plan digest changed after submission")

        return {
            "inbox": dict(inbox),
            "execution": dict(execution),
            "session": dict(session),
            "application": dict(application),
            "plan": plan,
        }

    @staticmethod
    def _evidence_verified(evidence: dict[str, Any], context: dict[str, Any]) -> bool:
        inbox = context["inbox"]
        execution = context["execution"]
        if evidence.get("synthetic") is not True:
            return False
        if evidence.get("verification_method") != VERIFICATION_METHOD:
            return False
        if str(evidence.get("provider") or "").upper() != str(inbox["provider"]).upper():
            return False
        if str(evidence.get("job_id") or "") != str(inbox["fixture_job_id"]):
            return False
        if str(evidence.get("provider_application_id") or "") != str(
            execution["provider_application_id"]
        ):
            return False
        try:
            observed_at = _parse_time(evidence.get("observed_at"))
            submitted_at = _parse_time(execution.get("completed_at"))
        except ValueError:
            return False
        if observed_at <= submitted_at:
            return False
        if str(evidence.get("provider_status") or "").strip().casefold() not in {
            "submitted",
            "received",
        }:
            return False
        if evidence.get("lookup_confirmed") is not True:
            return False
        observation_id = str(evidence.get("observation_id") or "").strip()
        return bool(observation_id and len(observation_id) <= 240)

    def _record_attempt(
        self,
        *,
        command_id: str,
        evidence: dict[str, Any],
        verified: bool,
    ) -> tuple[str, str]:
        safe = safe_evidence(dict(evidence))
        evidence_digest = _digest(safe)
        attempt_id = "synthetic-verification-attempt-" + _digest(
            [command_id, evidence_digest]
        )[:32]
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                """SELECT evidence_digest,verified
                   FROM synthetic_submission_verification_attempts
                   WHERE attempt_id=?""",
                (attempt_id,),
            ).fetchone()
            if prior is not None:
                if (
                    str(prior["evidence_digest"]) != evidence_digest
                    or bool(prior["verified"]) != bool(verified)
                ):
                    raise ValueError("Verification attempt replay conflict")
                return attempt_id, evidence_digest
            connection.execute(
                """INSERT INTO synthetic_submission_verification_attempts(
                       attempt_id,command_id,verification_method,observation_id,
                       observed_provider,observed_provider_application_id,
                       verified,evidence_json,evidence_digest,observed_at,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attempt_id,
                    command_id,
                    str(safe.get("verification_method") or VERIFICATION_METHOD),
                    str(safe.get("observation_id") or attempt_id),
                    str(safe.get("provider") or ""),
                    str(safe.get("provider_application_id") or ""),
                    int(bool(verified)),
                    canonical_json(safe),
                    evidence_digest,
                    str(safe.get("observed_at") or _now()),
                    _now(),
                ),
            )
        return attempt_id, evidence_digest

    @staticmethod
    def _chain_digest(connection: Any, session_id: str) -> str:
        rows = connection.execute(
            """SELECT event_id,event_type,replay_identity,evidence_json,
                      checkpoint_json,occurred_at
               FROM complete_application_execution_events
               WHERE session_id=? ORDER BY occurred_at,event_id""",
            (session_id,),
        ).fetchall()
        return _digest([dict(row) for row in rows])

    def verify(
        self,
        command_id: str,
        *,
        verifier: SyntheticSubmissionVerifier,
    ) -> SyntheticVerificationResult:
        command_id = str(command_id or "").strip()
        if not command_id:
            return SyntheticVerificationResult(
                "", False, "SUBMITTED", False, error="Synthetic submit command id is required"
            )
        if not _enabled():
            return SyntheticVerificationResult(
                command_id,
                False,
                "SUBMITTED",
                False,
                error="synthetic submission verification disabled",
            )

        prior_receipt = self._receipt(command_id)
        if prior_receipt is not None:
            return SyntheticVerificationResult(
                command_id,
                True,
                "VERIFIED",
                True,
                str(prior_receipt["receipt_id"]),
                str(prior_receipt["receipt_digest"]),
            )

        try:
            context = self._context(command_id)
        except (LookupError, ValueError) as error:
            return SyntheticVerificationResult(
                command_id,
                False,
                "SUBMITTED",
                False,
                error=str(error),
            )

        inbox = context["inbox"]
        execution = context["execution"]
        plan = context["plan"]

        try:
            raw = verifier.observe_submission(
                plan=plan,
                provider_application_id=str(execution["provider_application_id"]),
                target_url=str(inbox["target_url"]),
            )
        except Exception as error:
            raw = {
                "synthetic": True,
                "verification_method": VERIFICATION_METHOD,
                "observation_id": "verification-error-" + _digest(
                    [command_id, type(error).__name__, str(error)[:500]]
                )[:32],
                "provider": str(inbox["provider"]),
                "job_id": str(inbox["fixture_job_id"]),
                "provider_application_id": str(execution["provider_application_id"]),
                "provider_status": "unknown",
                "lookup_confirmed": False,
                "observed_at": _now(),
                "error_type": type(error).__name__,
                "error_message": str(error)[:500],
            }

        if not isinstance(raw, dict):
            raw = {
                "synthetic": True,
                "verification_method": VERIFICATION_METHOD,
                "observation_id": "verification-malformed-" + _digest(
                    [command_id, type(raw).__name__]
                )[:32],
                "provider": str(inbox["provider"]),
                "job_id": str(inbox["fixture_job_id"]),
                "provider_application_id": str(execution["provider_application_id"]),
                "provider_status": "unknown",
                "lookup_confirmed": False,
                "observed_at": _now(),
                "error_type": type(raw).__name__,
            }

        evidence = safe_evidence(dict(raw))
        verified = self._evidence_verified(evidence, context)
        attempt_id, evidence_digest = self._record_attempt(
            command_id=command_id,
            evidence=evidence,
            verified=verified,
        )
        if not verified:
            return SyntheticVerificationResult(
                command_id,
                False,
                "SUBMITTED",
                False,
                error="independent provider evidence did not verify submission",
            )

        verified_at = _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM synthetic_submission_receipts WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if prior is not None:
                return SyntheticVerificationResult(
                    command_id,
                    True,
                    "VERIFIED",
                    True,
                    str(prior["receipt_id"]),
                    str(prior["receipt_digest"]),
                )

            current_execution = connection.execute(
                "SELECT * FROM synthetic_submit_executions WHERE command_id=?",
                (command_id,),
            ).fetchone()
            current_session = connection.execute(
                "SELECT * FROM complete_application_sessions WHERE session_id=?",
                (execution["session_id"],),
            ).fetchone()
            current_application = connection.execute(
                "SELECT * FROM applications WHERE application_id=?",
                (execution["application_id"],),
            ).fetchone()
            if (
                current_execution is None
                or str(current_execution["state"]) != "SUBMITTED"
                or current_session is None
                or str(current_session["state"]) != "SUBMITTED"
                or current_application is None
                or str(current_application["status"]) != "SUBMITTED"
            ):
                raise RuntimeError("Submission state changed before verification committed")

            if connection.execute(
                """UPDATE complete_application_sessions
                   SET state='VERIFIED',state_version=state_version+1,updated_at=?
                   WHERE session_id=? AND state='SUBMITTED'""",
                (verified_at, execution["session_id"]),
            ).rowcount != 1:
                raise RuntimeError("Execution session changed during verification")

            if connection.execute(
                """UPDATE applications
                   SET status='VERIFIED',updated_at=?
                   WHERE application_id=? AND status='SUBMITTED'""",
                (verified_at, execution["application_id"]),
            ).rowcount != 1:
                raise RuntimeError("Application changed during verification")

            replay_identity = f"{command_id}:independent-verification:{evidence_digest}"
            event_evidence = safe_evidence(
                {
                    "command_id": command_id,
                    "attempt_id": attempt_id,
                    "synthetic": True,
                    "verification_method": VERIFICATION_METHOD,
                    "provider_application_id": execution["provider_application_id"],
                    "verification_evidence_digest": evidence_digest,
                }
            )
            connection.execute(
                """INSERT INTO complete_application_execution_events(
                       event_id,application_id,plan_id,session_id,provider,event_type,
                       replay_identity,evidence_json,checkpoint_json,occurred_at
                   ) VALUES (?,?,?,?,?,'VERIFIED',?,?,NULL,?)""",
                (
                    _event_id(replay_identity),
                    execution["application_id"],
                    execution["plan_id"],
                    execution["session_id"],
                    execution["provider"],
                    replay_identity,
                    canonical_json(event_evidence),
                    verified_at,
                ),
            )

            chain_digest = self._chain_digest(connection, str(execution["session_id"]))
            receipt = {
                "version": "munshi-synthetic-submission-receipt-v1",
                "command_id": command_id,
                "application_id": execution["application_id"],
                "plan_id": execution["plan_id"],
                "session_id": execution["session_id"],
                "review_id": inbox["review_id"],
                "approval_id": inbox["approval_id"],
                "provider": execution["provider"],
                "provider_application_id": execution["provider_application_id"],
                "submitted_at": execution["completed_at"],
                "verified_at": verified_at,
                "verification_method": VERIFICATION_METHOD,
                "verification_attempt_id": attempt_id,
                "verification_evidence_digest": evidence_digest,
                "plan_digest": inbox["plan_digest"],
                "review_digest": inbox["review_digest"],
                "approval_digest": inbox["approval_digest"],
                "prepared_package_digest": inbox["prepared_package_digest"],
                "browser_form_digest": inbox["browser_form_digest"],
                "resume_sha256": inbox["resume_sha256"],
                "cover_letter_sha256": inbox["cover_letter_sha256"],
                "answers_digest": _digest(plan.get("answers") or []),
                "execution_result_digest": execution["result_digest"],
                "execution_chain_digest": chain_digest,
                "verification_status": "VERIFIED",
            }
            receipt_digest = _digest(receipt)
            receipt_id = "synthetic-submission-receipt-" + receipt_digest[:32]
            connection.execute(
                """INSERT INTO synthetic_submission_receipts(
                       receipt_id,command_id,application_id,plan_id,session_id,
                       review_id,approval_id,provider,provider_application_id,
                       submitted_at,verified_at,verification_method,
                       verification_attempt_id,verification_evidence_json,
                       verification_evidence_digest,plan_digest,review_digest,
                       approval_digest,prepared_package_digest,browser_form_digest,
                       resume_sha256,cover_letter_sha256,answers_digest,
                       execution_result_digest,execution_chain_digest,
                       receipt_json,receipt_digest,verification_status,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    receipt_id,
                    command_id,
                    execution["application_id"],
                    execution["plan_id"],
                    execution["session_id"],
                    inbox["review_id"],
                    inbox["approval_id"],
                    execution["provider"],
                    execution["provider_application_id"],
                    execution["completed_at"],
                    verified_at,
                    VERIFICATION_METHOD,
                    attempt_id,
                    canonical_json(evidence),
                    evidence_digest,
                    inbox["plan_digest"],
                    inbox["review_digest"],
                    inbox["approval_digest"],
                    inbox["prepared_package_digest"],
                    inbox["browser_form_digest"],
                    inbox["resume_sha256"],
                    inbox["cover_letter_sha256"],
                    receipt["answers_digest"],
                    execution["result_digest"],
                    chain_digest,
                    canonical_json(receipt),
                    receipt_digest,
                    "VERIFIED",
                    verified_at,
                ),
            )

        return SyntheticVerificationResult(
            command_id,
            True,
            "VERIFIED",
            False,
            receipt_id,
            receipt_digest,
        )
