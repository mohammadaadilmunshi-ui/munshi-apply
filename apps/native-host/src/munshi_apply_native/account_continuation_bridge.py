from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .ats_account_lifecycle import ATSAccountLifecycle
from .complete_application_loop import (
    BrowserExecutionAdapter,
    CompleteApplicationLoopService,
    SessionResult,
)
from .database import Database


class AccountContinuationBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccountContinuationBinding:
    continuation_id: str
    account_id: str
    application_id: str
    execution_session_id: str
    provider: str
    target_fingerprint: str
    continuation_state: str
    account_state: str
    session_state: str
    target_url: str


def canonical_continuation_target_fingerprint(
    *,
    application_id: str,
    execution_session_id: str,
    provider: str,
    target_url: str,
) -> str:
    """Bind a continuation to the exact application execution target.

    The fingerprint deliberately includes the durable application and execution
    session identities. A valid account for the same ATS tenant therefore cannot
    be replayed into a different application or session.
    """
    values = {
        "application_id": application_id.strip(),
        "execution_session_id": execution_session_id.strip(),
        "provider": provider.strip().upper(),
        "target_url": target_url.strip(),
    }
    if not all(values.values()):
        raise AccountContinuationBridgeError(
            "Continuation target fingerprint requires complete exact bindings"
        )
    encoded = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class AccountContinuationBridge:
    """Resume a verified ATS account into its exact application session.

    This bridge owns no submit authority. It may only resume the reversible
    preparation path that already exists in CompleteApplicationLoopService.
    """

    _PREPARE_RETRY_STATES = {
        "SESSION_STARTING",
        "JOB_VERIFIED",
        "FORM_DISCOVERED",
        "PREPARING",
    }
    _DURABLE_RESUMED_STATES = {
        "NEEDS_INPUT",
        "READY_FOR_REVIEW",
        "READY_TO_SUBMIT",
    }

    def __init__(
        self,
        database: Database,
        loop_service: CompleteApplicationLoopService,
    ) -> None:
        self.database = database
        self.loop_service = loop_service
        self.lifecycle = ATSAccountLifecycle(database)

    def _binding(self, continuation_id: str) -> AccountContinuationBinding:
        if not isinstance(continuation_id, str) or not continuation_id.strip():
            raise AccountContinuationBridgeError("continuation_id is required")
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    c.continuation_id,
                    c.account_id,
                    c.application_id,
                    c.execution_session_id,
                    c.provider,
                    c.target_fingerprint,
                    c.state AS continuation_state,
                    a.state AS account_state,
                    s.application_id AS session_application_id,
                    s.provider AS session_provider,
                    s.state AS session_state,
                    p.application_id AS plan_application_id,
                    p.plan_json
                FROM ats_account_continuations c
                JOIN ats_account_state a
                  ON a.account_id = c.account_id
                JOIN complete_application_sessions s
                  ON s.session_id = c.execution_session_id
                JOIN career_os_application_plans p
                  ON p.plan_id = s.plan_id
                WHERE c.continuation_id = ?
                """,
                (continuation_id.strip(),),
            ).fetchone()
        if row is None:
            raise AccountContinuationBridgeError(
                "ATS continuation is not bound to an application execution session"
            )

        application_id = str(row["application_id"])
        if str(row["session_application_id"]) != application_id:
            raise AccountContinuationBridgeError(
                "ATS continuation application binding does not match execution session"
            )
        if str(row["plan_application_id"]) != application_id:
            raise AccountContinuationBridgeError(
                "ATS continuation application binding does not match accepted plan"
            )

        provider = str(row["provider"]).upper()
        if str(row["session_provider"]).upper() != provider:
            raise AccountContinuationBridgeError(
                "ATS continuation provider binding does not match execution session"
            )

        try:
            plan = json.loads(str(row["plan_json"]))
        except (TypeError, ValueError) as error:
            raise AccountContinuationBridgeError(
                "Accepted Application Plan could not be decoded"
            ) from error
        job = plan.get("job") if isinstance(plan, dict) else None
        target_url = job.get("apply_url") if isinstance(job, dict) else None
        if not isinstance(target_url, str) or not target_url.strip():
            raise AccountContinuationBridgeError(
                "Accepted Application Plan has no exact application target URL"
            )

        expected_fingerprint = canonical_continuation_target_fingerprint(
            application_id=application_id,
            execution_session_id=str(row["execution_session_id"]),
            provider=provider,
            target_url=target_url,
        )
        if str(row["target_fingerprint"]) != expected_fingerprint:
            raise AccountContinuationBridgeError(
                "ATS continuation target fingerprint does not match exact application target"
            )

        return AccountContinuationBinding(
            continuation_id=str(row["continuation_id"]),
            account_id=str(row["account_id"]),
            application_id=application_id,
            execution_session_id=str(row["execution_session_id"]),
            provider=provider,
            target_fingerprint=expected_fingerprint,
            continuation_state=str(row["continuation_state"]),
            account_state=str(row["account_state"]),
            session_state=str(row["session_state"]),
            target_url=target_url.strip(),
        )

    @staticmethod
    def _result(binding: AccountContinuationBinding) -> SessionResult:
        raise AssertionError("SessionResult must be loaded from the current session")

    def _current_result(self, session_id: str) -> SessionResult:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, application_id, plan_id, state, state_version
                FROM complete_application_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise AccountContinuationBridgeError("Execution session disappeared")
        return SessionResult(
            session_id=str(row["session_id"]),
            application_id=str(row["application_id"]),
            plan_id=str(row["plan_id"]),
            state=str(row["state"]),
            state_version=int(row["state_version"]),
        )

    def resume_verified(
        self,
        *,
        continuation_id: str,
        observed_at: str,
        adapter: BrowserExecutionAdapter,
    ) -> SessionResult:
        binding = self._binding(continuation_id)

        if binding.account_state not in {"VERIFIED", "AUTHENTICATED"}:
            raise AccountContinuationBridgeError(
                "ATS account is not verified for exact application continuation"
            )
        if binding.continuation_state not in {"READY", "CONSUMED"}:
            raise AccountContinuationBridgeError(
                "ATS continuation is not ready for exact application resume"
            )

        # This validates owner, accepted-plan integrity, state, and preparation
        # permissions before the continuation is consumed.
        self.loop_service.preflight_prepare_session(binding.execution_session_id)

        if (
            binding.continuation_state == "CONSUMED"
            and binding.session_state in self._DURABLE_RESUMED_STATES
        ):
            return self._current_result(binding.execution_session_id)

        consumed_now = binding.continuation_state == "READY"
        if consumed_now:
            self.lifecycle.consume_continuation(
                binding.continuation_id,
                observed_at,
            )

        try:
            result = self.loop_service.prepare_session(
                session_id=binding.execution_session_id,
                adapter=adapter,
            )
        except Exception:
            # Preparation is reversible. If an unexpected runtime failure occurs
            # before a durable resumed state exists, release only this exact
            # consumed continuation for a safe retry after restart.
            if consumed_now:
                with self.database.connect() as connection:
                    current = connection.execute(
                        "SELECT state FROM complete_application_sessions WHERE session_id = ?",
                        (binding.execution_session_id,),
                    ).fetchone()
                    if (
                        current is not None
                        and str(current["state"]) in self._PREPARE_RETRY_STATES
                    ):
                        connection.execute(
                            """
                            UPDATE ats_account_continuations
                            SET state = 'READY', updated_at = ?
                            WHERE continuation_id = ?
                              AND execution_session_id = ?
                              AND application_id = ?
                              AND state = 'CONSUMED'
                            """,
                            (
                                observed_at,
                                binding.continuation_id,
                                binding.execution_session_id,
                                binding.application_id,
                            ),
                        )
            raise

        if result.state in {"NEEDS_INPUT", "READY_FOR_REVIEW", "READY_TO_SUBMIT"}:
            self.lifecycle.mark_authenticated(
                binding.account_id,
                binding.application_id,
                observed_at,
            )
        return result
