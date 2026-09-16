from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Protocol

from .ats_account_lifecycle import ATSAccountLifecycle
from .database import Database
from .mail_artifact_broker import ClaimedMailArtifact, MailArtifactBrokerClient


class AccountVerificationRuntimeError(RuntimeError):
    pass


class VerificationArtifactExecutor(Protocol):
    def apply_verification(
        self,
        *,
        artifact_kind: str,
        artifact: str,
    ) -> bool: ...


@dataclass(frozen=True)
class VerificationRuntimeResult:
    challenge_id: str
    account_id: str
    application_id: str
    continuation_id: str
    account_state: str
    continuation_state: str
    artifact_kind: str


_BROKER_TO_LIFECYCLE_KIND = {
    "EMAIL_VERIFICATION_CODE": "EMAIL_CODE",
    "EMAIL_VERIFICATION_LINK": "EMAIL_LINK",
    "PASSWORD_RESET_LINK": "PASSWORD_RESET_LINK",
    "MAGIC_LOGIN_LINK": "MAGIC_LOGIN_LINK",
}


class AccountVerificationRuntime:
    """Consume one Hunter artifact and advance only its exact ATS continuation.

    Raw codes, links, and claim tokens remain in local variables only. Successful
    email verification proves the ATS account, not application submission authority.
    Any ambiguous post-execution broker state is converted to ISSUE so the artifact
    is never blindly replayed.
    """

    def __init__(
        self,
        database: Database,
        broker: MailArtifactBrokerClient,
    ) -> None:
        self.database = database
        self.lifecycle = ATSAccountLifecycle(database)
        self.broker = broker

    def _challenge(self, challenge_id: str) -> dict[str, object]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.*, c.state AS continuation_state
                FROM ats_verification_challenges v
                JOIN ats_account_continuations c
                  ON c.continuation_id = v.continuation_id
                WHERE v.challenge_id = ?
                """,
                (challenge_id,),
            ).fetchone()
        if row is None:
            raise AccountVerificationRuntimeError("Unknown verification challenge")
        return dict(row)

    def _issue(
        self,
        *,
        challenge: dict[str, object],
        issue_code: str,
        observed_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE ats_verification_challenges
                SET state = 'ISSUE', updated_at = ?
                WHERE challenge_id = ? AND state IN ('READY', 'CLAIMED')
                """,
                (observed_at, str(challenge["challenge_id"])),
            )
            connection.execute(
                """
                UPDATE ats_account_continuations
                SET state = 'ISSUE', issue_code = ?, updated_at = ?
                WHERE continuation_id = ? AND state IN ('PENDING', 'READY')
                """,
                (
                    issue_code,
                    observed_at,
                    str(challenge["continuation_id"]),
                ),
            )
            connection.execute(
                """
                UPDATE ats_account_state
                SET state = 'FAILED_SAFE', issue_code = ?, issue_detail = NULL,
                    version = version + 1, updated_at = ?
                WHERE account_id = ?
                """,
                (issue_code, observed_at, str(challenge["account_id"])),
            )

    def _requeue(self, challenge_id: str, observed_at: str) -> None:
        self.lifecycle.requeue_claim(challenge_id, observed_at)

    def execute(
        self,
        *,
        challenge_id: str,
        broker_request_id: str,
        application_key: str,
        observed_at: str,
        executor: VerificationArtifactExecutor,
    ) -> VerificationRuntimeResult:
        challenge = self._challenge(challenge_id)
        if str(challenge["state"]) != "READY":
            raise AccountVerificationRuntimeError(
                "Verification challenge is not ready for one-time execution"
            )
        if str(challenge["continuation_state"]) not in {"PENDING", "READY"}:
            raise AccountVerificationRuntimeError(
                "Verification continuation is not resumable"
            )
        if not challenge.get("artifact_digest"):
            raise AccountVerificationRuntimeError(
                "Verification challenge has no Hunter artifact digest"
            )

        claimed_local = self.lifecycle.claim_verification(challenge_id, observed_at)
        if claimed_local.get("claimedNow") is not True:
            raise AccountVerificationRuntimeError(
                "Verification challenge was not exclusively claimed"
            )

        try:
            claimed: ClaimedMailArtifact = self.broker.claim(
                request_id=broker_request_id,
                application_key=application_key,
            )
        except Exception:
            self._requeue(challenge_id, observed_at)
            raise

        expected_kind = _BROKER_TO_LIFECYCLE_KIND.get(claimed.artifact_kind)
        actual_kind = str(challenge["kind"]).upper()
        digest_matches = hmac.compare_digest(
            claimed.artifact_digest,
            str(challenge["artifact_digest"]).lower(),
        )
        if expected_kind != actual_kind or not digest_matches:
            self._issue(
                challenge=challenge,
                issue_code="MAIL_ARTIFACT_BINDING_MISMATCH",
                observed_at=observed_at,
            )
            raise AccountVerificationRuntimeError(
                "Hunter artifact does not match the exact verification challenge"
            )

        try:
            verified = executor.apply_verification(
                artifact_kind=claimed.artifact_kind,
                artifact=claimed.artifact,
            )
        except Exception:
            self._issue(
                challenge=challenge,
                issue_code="VERIFICATION_EXECUTION_AMBIGUOUS",
                observed_at=observed_at,
            )
            raise
        if verified is not True:
            self._issue(
                challenge=challenge,
                issue_code="VERIFICATION_EXECUTION_UNCONFIRMED",
                observed_at=observed_at,
            )
            raise AccountVerificationRuntimeError(
                "ATS verification execution was not positively confirmed"
            )

        # Persist the external fact before broker cleanup. If cleanup is ambiguous,
        # the continuation is moved to ISSUE and the one-time value is never replayed.
        self.lifecycle.mark_verified(
            str(challenge["account_id"]),
            str(challenge["application_id"]),
            observed_at,
        )
        try:
            self.broker.consume(
                request_id=broker_request_id,
                application_key=application_key,
                claim_token=claimed.claim_token,
            )
        except Exception:
            self._issue(
                challenge=challenge,
                issue_code="MAIL_ARTIFACT_CONSUME_AMBIGUOUS",
                observed_at=observed_at,
            )
            raise

        self.lifecycle.consume_verification(challenge_id, observed_at)
        continuation = self.lifecycle.mark_continuation_ready(
            str(challenge["continuation_id"]),
            observed_at,
        )
        snapshot = self.lifecycle.snapshot(str(challenge["account_id"]))
        return VerificationRuntimeResult(
            challenge_id=challenge_id,
            account_id=str(challenge["account_id"]),
            application_id=str(challenge["application_id"]),
            continuation_id=str(challenge["continuation_id"]),
            account_state=str(snapshot["state"]),
            continuation_state=str(continuation["state"]),
            artifact_kind=claimed.artifact_kind,
        )
