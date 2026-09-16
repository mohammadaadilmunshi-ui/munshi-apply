from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.account_store import AccountStore
from munshi_apply_native.ats_account_lifecycle import (
    ATSAccountLifecycle,
    ATSAccountLifecycleError,
)
from munshi_apply_native.database import Database


NOW = "2026-09-16T12:00:00+00:00"
LATER = "2026-09-16T12:01:00+00:00"


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-1', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (NOW, NOW),
        )
    AccountStore(database).upsert(
        {
            "accountId": "account-1",
            "employer": "Example",
            "portalUrl": "https://wd5.myworkdayjobs.com/example/login",
            "email": "u_abcdefghijklmnop@mail.munshi.systems",
            "exists": False,
            "applicationId": "app-1",
            "observedAt": NOW,
        }
    )
    return database


def provision(lifecycle: ATSAccountLifecycle) -> None:
    lifecycle.provision(
        {
            "accountId": "account-1",
            "provider": "workday",
            "credentialRef": "credref:v1:abcdefghijklmnop",
            "mailAlias": "u_abcdefghijklmnop@mail.munshi.systems",
            "observedAt": NOW,
        }
    )


def bind(lifecycle: ATSAccountLifecycle) -> None:
    lifecycle.bind_continuation(
        {
            "continuationId": "continuation-1",
            "accountId": "account-1",
            "applicationId": "app-1",
            "executionSessionId": "session-1",
            "provider": "workday",
            "targetFingerprint": "sha256:application-target",
            "observedAt": NOW,
        }
    )


def test_account_creation_verification_and_continuation_survive_restart(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    lifecycle = ATSAccountLifecycle(database)
    provision(lifecycle)
    bind(lifecycle)

    lifecycle.begin_creation("account-1", NOW)
    created = lifecycle.mark_created(
        "account-1", "app-1", NOW, verification_required=True
    )
    assert created["state"] == "VERIFICATION_PENDING"
    assert [event["event_type"] for event in created["events"]] == [
        "ATS_ACCOUNT_CREATED",
        "ATS_ACCOUNT_VERIFICATION_PENDING",
    ]

    lifecycle.start_verification(
        {
            "challengeId": "challenge-1",
            "accountId": "account-1",
            "applicationId": "app-1",
            "continuationId": "continuation-1",
            "kind": "EMAIL_CODE",
            "observedAt": NOW,
            "expiresAt": "2026-09-16T12:10:00+00:00",
        }
    )
    lifecycle.mark_verification_ready(
        {
            "challengeId": "challenge-1",
            "mailEventId": "mail-event-opaque-1",
            "artifactDigest": "a" * 64,
            "observedAt": LATER,
        }
    )

    claimed = lifecycle.claim_verification("challenge-1", LATER)
    assert claimed["claimedNow"] is True
    duplicate_claim = lifecycle.claim_verification("challenge-1", LATER)
    assert duplicate_claim["claimedNow"] is False

    # A fresh service instance sees the durable claim, re-resolves the trusted
    # mail event externally, and may safely requeue without storing the OTP.
    restarted = ATSAccountLifecycle(database)
    assert restarted.snapshot("account-1")["verificationChallenges"][0]["state"] == "CLAIMED"
    assert restarted.requeue_claim("challenge-1", LATER)["state"] == "READY"
    assert restarted.claim_verification("challenge-1", LATER)["claimedNow"] is True
    assert restarted.consume_verification("challenge-1", LATER)["state"] == "CONSUMED"

    verified = restarted.mark_verified("account-1", "app-1", LATER)
    assert verified["state"] == "VERIFIED"
    assert verified["events"][-1]["event_type"] == "ATS_ACCOUNT_VERIFIED"

    ready = restarted.mark_continuation_ready("continuation-1", LATER)
    assert ready["state"] == "READY"
    consumed = restarted.consume_continuation("continuation-1", LATER)
    assert consumed["state"] == "CONSUMED"

    authenticated = restarted.mark_authenticated("account-1", "app-1", LATER)
    assert authenticated["state"] == "AUTHENTICATED"
    assert authenticated["events"][-1]["event_type"] == "ATS_ACCOUNT_AUTHENTICATED"


def test_no_raw_verification_or_password_material_is_durable(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    lifecycle = ATSAccountLifecycle(database)
    provision(lifecycle)

    with database.connect() as connection:
        account_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(ats_account_state)")
        }
        challenge_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(ats_verification_challenges)")
        }
    assert "password" not in account_columns
    assert "secret" not in account_columns
    assert "otp" not in challenge_columns
    assert "code" not in challenge_columns
    assert "url" not in challenge_columns
    assert "token" not in challenge_columns

    with pytest.raises(ATSAccountLifecycleError, match="Secret"):
        lifecycle.provision(
            {
                "accountId": "account-1",
                "provider": "workday",
                "password": "never-store-me",
                "observedAt": NOW,
            }
        )

    bind(lifecycle)
    lifecycle.start_verification(
        {
            "challengeId": "challenge-1",
            "accountId": "account-1",
            "applicationId": "app-1",
            "continuationId": "continuation-1",
            "kind": "EMAIL_LINK",
            "observedAt": NOW,
        }
    )
    with pytest.raises(ATSAccountLifecycleError, match="Secret"):
        lifecycle.mark_verification_ready(
            {
                "challengeId": "challenge-1",
                "mailEventId": "mail-event-1",
                "artifactDigest": "b" * 64,
                "verificationUrl": "https://example.test/verify?token=raw",
                "observedAt": LATER,
            }
        )


def test_security_challenges_fail_to_preserved_issue_state(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    lifecycle = ATSAccountLifecycle(database)
    provision(lifecycle)
    bind(lifecycle)
    lifecycle.begin_creation("account-1", NOW)

    issue = lifecycle.security_issue(
        {
            "accountId": "account-1",
            "applicationId": "app-1",
            "continuationId": "continuation-1",
            "challengeKind": "TOTP",
            "observedAt": LATER,
        }
    )
    assert issue["state"] == "NEEDS_USER_ACTION"
    assert issue["issue_code"] == "SECURITY_INTERVENTION_TOTP"
    assert issue["continuations"][0]["state"] == "ISSUE"
    assert issue["events"][-1]["event_type"] == "ATS_ACCOUNT_ISSUE"

    with pytest.raises(ATSAccountLifecycleError, match="candidate-controlled"):
        lifecycle.start_verification(
            {
                "challengeId": "challenge-security",
                "accountId": "account-1",
                "applicationId": "app-1",
                "continuationId": "continuation-1",
                "kind": "SMS",
                "observedAt": LATER,
            }
        )
