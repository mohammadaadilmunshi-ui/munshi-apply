"""Hunter-command-native synthetic submit execution.

Phase H consumes the single-use authority created by Phase G. It is default-off,
synthetic-only, and never marks an application VERIFIED or creates a submission
receipt. Independent verification and receipt authority are later tranches.
"""

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
from .synthetic_submit_command_inbox import SyntheticSubmitCommandInbox

SYNTHETIC_SUBMIT_EXECUTION_ENV = "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED"

_TERMINAL_STATES = frozenset(
    {"SUBMITTED", "SUBMISSION_UNVERIFIED", "BLOCKED", "FAILED_SAFELY"}
)


def _enabled() -> bool:
    return str(os.getenv(SYNTHETIC_SUBMIT_EXECUTION_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()


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


class SyntheticSubmitExecutionAdapter(Protocol):
    def inspect_submission(self, *, plan: dict[str, Any]) -> dict[str, Any]: ...

    def submit(
        self,
        *,
        plan: dict[str, Any],
        review: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SyntheticSubmitExecutionResult:
    command_id: str
    state: str
    replayed: bool
    action_executed: bool | None
    provider_application_id: str | None
    error: str | None = None


class SyntheticSubmitExecutor:
    def __init__(self, database: Database, *, secret: str) -> None:
        self.database = database
        self.inbox = SyntheticSubmitCommandInbox(database, secret=secret)

    def _load_plan(self, plan_id: str, tenant_id: str, user_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM career_os_application_plans
                   WHERE plan_id=? AND tenant_id=? AND user_id=?""",
                (plan_id, tenant_id, user_id),
            ).fetchone()
        if row is None:
            raise LookupError("Accepted Application Plan was not found")
        try:
            plan = json.loads(str(row["plan_json"]))
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("Stored Application Plan is malformed") from error
        if not isinstance(plan, dict):
            raise ValueError("Stored Application Plan is malformed")
        if _sha256_json(_plan_digest_payload(plan)) != str(row["plan_digest"]):
            raise ValueError("Stored Application Plan integrity failure")
        return plan

    def _execution(self, command_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM synthetic_submit_executions WHERE command_id=?",
                (command_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _validate_observation(
        observation: dict[str, Any],
        *,
        envelope: dict[str, Any],
        plan: dict[str, Any],
    ) -> None:
        if observation.get("security_checkpoint"):
            raise ValueError("Security checkpoint blocks synthetic submission")
        if observation.get("supported") is not True:
            raise ValueError("Synthetic provider final submission is unsupported")
        if observation.get("plan_current") is not True:
            raise ValueError("Current Hunter plan validation is required")
        if str(observation.get("provider") or "").upper() != str(envelope["provider"]):
            raise ValueError("Browser provider changed after Hunter approval")
        if str(observation.get("job_id") or "") != str(envelope["fixture_job_id"]):
            raise ValueError("Browser job changed after Hunter approval")
        if str(observation.get("current_url") or "") != str(envelope["target_url"]):
            raise ValueError("Browser destination changed after Hunter approval")
        if str(observation.get("form_digest") or "") != str(
            envelope["browser_form_digest"]
        ):
            raise ValueError("Browser form changed after Hunter approval")
        if observation.get("resume_uploaded") is not True:
            raise ValueError("Browser resume is no longer uploaded")
        if str(observation.get("resume_sha256") or "") != str(envelope["resume_sha256"]):
            raise ValueError("Browser resume changed after Hunter approval")

        cover = plan.get("cover_letter")
        if isinstance(cover, dict):
            if observation.get("cover_letter_uploaded") is not True:
                raise ValueError("Browser cover letter is no longer uploaded")
            if str(observation.get("cover_letter_sha256") or "") != str(
                envelope.get("cover_letter_sha256") or ""
            ):
                raise ValueError("Browser cover letter changed after Hunter approval")

        if observation.get("unresolved") or observation.get("validation_errors"):
            raise ValueError("Browser form has unresolved required inputs")
        if observation.get("completed_required_fields") != observation.get(
            "required_fields"
        ):
            raise ValueError("Browser form required fields are incomplete")

    @staticmethod
    def _correlated_submission(
        result: dict[str, Any],
        *,
        envelope: dict[str, Any],
    ) -> bool:
        if result.get("action_executed") is not True:
            return False
        evidence = result.get("success_evidence")
        if not isinstance(evidence, dict):
            return False
        if str(evidence.get("provider") or "").upper() != str(envelope["provider"]):
            return False
        if str(evidence.get("job_id") or "") != str(envelope["fixture_job_id"]):
            return False
        provider_application_id = str(
            evidence.get("provider_application_id") or ""
        ).strip()
        response_status = evidence.get("response_status")
        response_url = str(evidence.get("response_url") or "")
        submit_action = str(evidence.get("submit_action") or "")
        submit_method = str(evidence.get("submit_method") or "").upper()
        if not provider_application_id:
            return False
        if not isinstance(response_status, int) or not 200 <= response_status < 300:
            return False
        if submit_method != "POST":
            return False
        if submit_action != str(envelope["target_url"]):
            return False
        if response_url != submit_action:
            return False
        return bool(
            evidence.get("completion_marker")
            and evidence.get("submission_response_marker")
        )

    @staticmethod
    def _review_adapter_view(envelope: dict[str, Any]) -> dict[str, Any]:
        return {
            "review_id": envelope["review_id"],
            "review_digest": envelope["review_digest"],
            "destination_url": envelope["target_url"],
            "browser_verification": {
                "form_digest": envelope["browser_form_digest"],
            },
            "submission_authority": True,
            "synthetic": True,
        }

    def _finish(
        self,
        *,
        command_id: str,
        state: str,
        action_executed: bool | None,
        result: dict[str, Any],
    ) -> SyntheticSubmitExecutionResult:
        if state not in _TERMINAL_STATES:
            raise ValueError("Synthetic submit execution terminal state is invalid")

        safe_result = safe_evidence(dict(result))
        evidence = safe_result.get("success_evidence")
        safe_success = evidence if isinstance(evidence, dict) else {}
        result_digest = _digest(safe_result)
        completed_at = _now()

        provider_application_id = str(
            safe_result.get("provider_application_id")
            or safe_success.get("provider_application_id")
            or ""
        ).strip() or None
        response_status = safe_success.get("response_status")
        if not isinstance(response_status, int):
            response_status = None
        submit_action = str(safe_success.get("submit_action") or "").strip() or None
        submit_method = str(safe_success.get("submit_method") or "").strip() or None
        submission_url = str(safe_result.get("submission_url") or "").strip() or None

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            execution = connection.execute(
                "SELECT * FROM synthetic_submit_executions WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if execution is None:
                raise LookupError("Synthetic submit execution was not started")
            if str(execution["state"]) != "SUBMITTING":
                existing = dict(execution)
                return SyntheticSubmitExecutionResult(
                    command_id=command_id,
                    state=str(existing["state"]),
                    replayed=True,
                    action_executed=(
                        None
                        if existing["action_executed"] is None
                        else bool(existing["action_executed"])
                    ),
                    provider_application_id=(
                        str(existing["provider_application_id"])
                        if existing["provider_application_id"]
                        else None
                    ),
                )

            updated = connection.execute(
                """UPDATE synthetic_submit_executions
                   SET state=?,completed_at=?,action_executed=?,submission_url=?,
                       provider_application_id=?,response_status=?,submit_action=?,
                       submit_method=?,success_evidence_json=?,result_json=?,result_digest=?
                   WHERE command_id=? AND state='SUBMITTING'""",
                (
                    state,
                    completed_at,
                    (
                        None
                        if action_executed is None
                        else int(bool(action_executed))
                    ),
                    submission_url,
                    provider_application_id,
                    response_status,
                    submit_action,
                    submit_method,
                    canonical_json(safe_success),
                    canonical_json(safe_result),
                    result_digest,
                    command_id,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Synthetic submit execution changed concurrently")

            session_id = str(execution["session_id"])
            application_id = str(execution["application_id"])
            session_updated = connection.execute(
                """UPDATE complete_application_sessions
                   SET state=?,state_version=state_version+1,updated_at=?
                   WHERE session_id=? AND state='SUBMITTING'""",
                (state, completed_at, session_id),
            )
            if session_updated.rowcount != 1:
                raise RuntimeError("Execution session changed during synthetic submission")

            if state == "SUBMITTED":
                application_updated = connection.execute(
                    """UPDATE applications
                       SET status=?,submitted_at=COALESCE(submitted_at,?),updated_at=?
                       WHERE application_id=? AND status='SUBMITTING'""",
                    (state, completed_at, completed_at, application_id),
                )
            else:
                application_updated = connection.execute(
                    """UPDATE applications
                       SET status=?,updated_at=?
                       WHERE application_id=? AND status='SUBMITTING'""",
                    (state, completed_at, application_id),
                )
            if application_updated.rowcount != 1:
                raise RuntimeError("Application changed during synthetic submission")

            replay_identity = f"{command_id}:synthetic-submit-outcome:{state}"
            event_id = _event_id(replay_identity)
            event_evidence = {
                "command_id": command_id,
                "synthetic": True,
                "state": state,
                "action_executed": action_executed,
                "provider_application_id": provider_application_id,
                "result_digest": result_digest,
            }
            connection.execute(
                """INSERT INTO complete_application_execution_events(
                       event_id,application_id,plan_id,session_id,provider,event_type,
                       replay_identity,evidence_json,checkpoint_json,occurred_at
                   ) VALUES (?,?,?,?,?,?,?,?,NULL,?)""",
                (
                    event_id,
                    application_id,
                    str(execution["plan_id"]),
                    session_id,
                    str(execution["provider"]),
                    state,
                    replay_identity,
                    canonical_json(safe_evidence(event_evidence)),
                    completed_at,
                ),
            )

        return SyntheticSubmitExecutionResult(
            command_id=command_id,
            state=state,
            replayed=False,
            action_executed=action_executed,
            provider_application_id=provider_application_id,
        )

    def execute(
        self,
        command_id: str,
        *,
        now: int,
        adapter: SyntheticSubmitExecutionAdapter,
    ) -> SyntheticSubmitExecutionResult:
        if not _enabled():
            return SyntheticSubmitExecutionResult(
                command_id=str(command_id),
                state="READY_TO_SUBMIT",
                replayed=False,
                action_executed=False,
                provider_application_id=None,
                error="synthetic submit execution disabled",
            )

        claim = self.inbox.claim_for_execution(command_id, now=now)
        if not claim.claimed:
            if claim.replayed:
                existing = self._execution(str(command_id))
                if existing is not None:
                    return SyntheticSubmitExecutionResult(
                        command_id=str(command_id),
                        state=str(existing["state"]),
                        replayed=True,
                        action_executed=(
                            None
                            if existing["action_executed"] is None
                            else bool(existing["action_executed"])
                        ),
                        provider_application_id=(
                            str(existing["provider_application_id"])
                            if existing["provider_application_id"]
                            else None
                        ),
                        error=claim.error,
                    )
            return SyntheticSubmitExecutionResult(
                command_id=str(command_id),
                state="READY_TO_SUBMIT",
                replayed=claim.replayed,
                action_executed=False,
                provider_application_id=None,
                error=claim.error or "synthetic submit command could not be claimed",
            )

        envelope = dict(claim.envelope or {})
        plan = self._load_plan(
            str(envelope["plan_id"]),
            str(envelope["tenant_id"]),
            str(envelope["user_id"]),
        )

        try:
            observation = adapter.inspect_submission(plan=plan)
            self._validate_observation(
                observation,
                envelope=envelope,
                plan=plan,
            )
        except Exception as error:
            return self._finish(
                command_id=str(command_id),
                state="FAILED_SAFELY",
                action_executed=False,
                result={
                    "action_executed": False,
                    "failure_stage": "pre_submit_revalidation",
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:500],
                },
            )

        try:
            result = adapter.submit(
                plan=plan,
                review=self._review_adapter_view(envelope),
            )
        except Exception as error:
            return self._finish(
                command_id=str(command_id),
                state="SUBMISSION_UNVERIFIED",
                action_executed=None,
                result={
                    "action_executed": None,
                    "failure_stage": "submit_action_ambiguous",
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:500],
                },
            )

        if not isinstance(result, dict):
            return self._finish(
                command_id=str(command_id),
                state="SUBMISSION_UNVERIFIED",
                action_executed=None,
                result={
                    "action_executed": None,
                    "failure_stage": "submit_result_malformed",
                    "error_type": type(result).__name__,
                },
            )

        safe_result = dict(result)
        action_executed = safe_result.get("action_executed") is True
        requested_status = str(safe_result.get("verification_status") or "").upper()

        if not action_executed and requested_status == "BLOCKED":
            state = "BLOCKED"
        elif not action_executed:
            state = "FAILED_SAFELY"
        elif self._correlated_submission(safe_result, envelope=envelope):
            state = "SUBMITTED"
        else:
            state = "SUBMISSION_UNVERIFIED"

        return self._finish(
            command_id=str(command_id),
            state=state,
            action_executed=action_executed,
            result=safe_result,
        )
