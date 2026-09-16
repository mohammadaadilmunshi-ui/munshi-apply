from __future__ import annotations

import hashlib

import pytest

from test_account_umbrella_e2e_v1 import _lifecycle

from munshi_apply_native.account_verification_runtime import (
    AccountVerificationRuntime,
    AccountVerificationRuntimeError,
)
from munshi_apply_native.mail_artifact_broker import ClaimedMailArtifact

NOW = "2026-09-16T22:00:00+00:00"
LATER = "2026-09-16T22:01:00+00:00"


class FakeBroker:
    def __init__(self, *, artifact_kind: str, artifact: str) -> None:
        self.artifact_kind = artifact_kind
        self.artifact = artifact
        self.digest = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
        self.claims = 0
        self.consumes = 0
        self.fail_consume = False

    def claim(self, *, request_id: str, application_key: str) -> ClaimedMailArtifact:
        assert request_id == "hunter-request-1"
        assert application_key == "app-key-1"
        self.claims += 1
        return ClaimedMailArtifact(
            request_id=request_id,
            artifact_kind=self.artifact_kind,
            artifact_digest=self.digest,
            artifact=self.artifact,
            claim_token="opaque-claim-token",
            lease_expires_at="2026-09-16T22:10:00+00:00",
        )

    def consume(
        self,
        *,
        request_id: str,
        application_key: str,
        claim_token: str,
    ) -> None:
        assert request_id == "hunter-request-1"
        assert application_key == "app-key-1"
        assert claim_token == "opaque-claim-token"
        self.consumes += 1
        if self.fail_consume:
            raise RuntimeError("synthetic consume response lost")


class FakeExecutor:
    def __init__(self, *, verified: bool = True) -> None:
        self.verified = verified
        self.calls = 0
        self.last_artifact: str | None = None

    def apply_verification(self, *, artifact_kind: str, artifact: str) -> bool:
        assert artifact_kind in {
            "EMAIL_VERIFICATION_CODE",
            "EMAIL_VERIFICATION_LINK",
            "PASSWORD_RESET_LINK",
            "MAGIC_LOGIN_LINK",
        }
        self.calls += 1
        self.last_artifact = artifact
        return self.verified


def _ready_challenge(tmp_path, *, kind: str, digest: str):
    database, lifecycle = _lifecycle(tmp_path)
    lifecycle.begin_creation("account-umbrella", NOW)
    lifecycle.mark_created(
        "account-umbrella",
        "app-umbrella",
        NOW,
        verification_required=True,
    )
    lifecycle.start_verification(
        {
            "challengeId": "challenge-runtime",
            "accountId": "account-umbrella",
            "applicationId": "app-umbrella",
            "continuationId": "continuation-umbrella",
            "kind": kind,
            "observedAt": NOW,
            "expiresAt": "2026-09-16T22:10:00+00:00",
        }
    )
    lifecycle.mark_verification_ready(
        {
            "challengeId": "challenge-runtime",
            "mailEventId": "mail-event-runtime",
            "artifactDigest": digest,
            "observedAt": LATER,
        }
    )
    return database, lifecycle


def test_magic_link_is_consumed_once_then_exact_continuation_becomes_ready(
    tmp_path,
) -> None:
    artifact = "https://ats.example.test/magic/opaque"
    broker = FakeBroker(artifact_kind="MAGIC_LOGIN_LINK", artifact=artifact)
    database, lifecycle = _ready_challenge(
        tmp_path,
        kind="MAGIC_LOGIN_LINK",
        digest=broker.digest,
    )
    executor = FakeExecutor()

    result = AccountVerificationRuntime(database, broker).execute(
        challenge_id="challenge-runtime",
        broker_request_id="hunter-request-1",
        application_key="app-key-1",
        observed_at=LATER,
        executor=executor,
    )

    assert result.account_state == "VERIFIED"
    assert result.continuation_state == "READY"
    assert broker.claims == 1
    assert broker.consumes == 1
    assert executor.calls == 1
    assert executor.last_artifact == artifact
    assert artifact not in repr(result)
    snapshot = lifecycle.snapshot("account-umbrella")
    assert snapshot["verificationChallenges"][0]["state"] == "CONSUMED"
    assert snapshot["continuations"][0]["state"] == "READY"


def test_artifact_digest_mismatch_fails_closed_before_browser_execution(
    tmp_path,
) -> None:
    broker = FakeBroker(artifact_kind="EMAIL_VERIFICATION_CODE", artifact="482915")
    database, lifecycle = _ready_challenge(
        tmp_path,
        kind="EMAIL_CODE",
        digest="0" * 64,
    )
    executor = FakeExecutor()

    with pytest.raises(AccountVerificationRuntimeError, match="exact verification"):
        AccountVerificationRuntime(database, broker).execute(
            challenge_id="challenge-runtime",
            broker_request_id="hunter-request-1",
            application_key="app-key-1",
            observed_at=LATER,
            executor=executor,
        )

    assert executor.calls == 0
    assert broker.consumes == 0
    snapshot = lifecycle.snapshot("account-umbrella")
    assert snapshot["state"] == "FAILED_SAFE"
    assert snapshot["continuations"][0]["state"] == "ISSUE"
    assert snapshot["verificationChallenges"][0]["state"] == "ISSUE"


def test_unconfirmed_verification_never_advances_continuation(tmp_path) -> None:
    artifact = "https://ats.example.test/reset/opaque"
    broker = FakeBroker(artifact_kind="PASSWORD_RESET_LINK", artifact=artifact)
    database, lifecycle = _ready_challenge(
        tmp_path,
        kind="PASSWORD_RESET_LINK",
        digest=broker.digest,
    )
    executor = FakeExecutor(verified=False)

    with pytest.raises(AccountVerificationRuntimeError, match="not positively confirmed"):
        AccountVerificationRuntime(database, broker).execute(
            challenge_id="challenge-runtime",
            broker_request_id="hunter-request-1",
            application_key="app-key-1",
            observed_at=LATER,
            executor=executor,
        )

    assert executor.calls == 1
    assert broker.consumes == 0
    snapshot = lifecycle.snapshot("account-umbrella")
    assert snapshot["continuations"][0]["state"] == "ISSUE"


def test_ambiguous_broker_consume_never_replays_used_artifact(tmp_path) -> None:
    artifact = "https://ats.example.test/verify/opaque"
    broker = FakeBroker(artifact_kind="EMAIL_VERIFICATION_LINK", artifact=artifact)
    broker.fail_consume = True
    database, lifecycle = _ready_challenge(
        tmp_path,
        kind="EMAIL_LINK",
        digest=broker.digest,
    )
    executor = FakeExecutor()

    with pytest.raises(RuntimeError, match="response lost"):
        AccountVerificationRuntime(database, broker).execute(
            challenge_id="challenge-runtime",
            broker_request_id="hunter-request-1",
            application_key="app-key-1",
            observed_at=LATER,
            executor=executor,
        )

    assert executor.calls == 1
    assert broker.claims == 1
    assert broker.consumes == 1
    snapshot = lifecycle.snapshot("account-umbrella")
    assert snapshot["state"] == "FAILED_SAFE"
    assert snapshot["continuations"][0]["state"] == "ISSUE"
    assert snapshot["verificationChallenges"][0]["state"] == "ISSUE"
