from __future__ import annotations

from pathlib import Path

from munshi_apply_native.account_store import AccountStore
from munshi_apply_native.account_teach_service import AccountTeachService
from munshi_apply_native.ats_account_lifecycle import ATSAccountLifecycle
from munshi_apply_native.database import Database

NOW = "2026-09-16T12:00:00+00:00"
LATER = "2026-09-16T12:01:00+00:00"


def _database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "umbrella.sqlite", migrations)
    database.migrate()
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO applications(
                   application_id,job_id,status,resume_id,job_signal_score,
                   submitted_at,created_at,updated_at
               ) VALUES('app-umbrella',NULL,'DETECTED',NULL,NULL,NULL,?,?)""",
            (NOW, NOW),
        )
    AccountStore(database).upsert(
        {
            "accountId": "account-umbrella",
            "employer": "Example",
            "portalUrl": "https://wd5.myworkdayjobs.com/example/login",
            "email": "u_abcdefghijklmnop@mail.munshi.systems",
            "exists": False,
            "applicationId": "app-umbrella",
            "observedAt": NOW,
        }
    )
    return database


def _lifecycle(tmp_path: Path) -> tuple[Database, ATSAccountLifecycle]:
    database = _database(tmp_path)
    lifecycle = ATSAccountLifecycle(database)
    lifecycle.provision(
        {
            "accountId": "account-umbrella",
            "provider": "workday",
            "credentialRef": "credref:v1:abcdefghijklmnop",
            "mailAlias": "u_abcdefghijklmnop@mail.munshi.systems",
            "observedAt": NOW,
        }
    )
    lifecycle.bind_continuation(
        {
            "continuationId": "continuation-umbrella",
            "accountId": "account-umbrella",
            "applicationId": "app-umbrella",
            "executionSessionId": "session-umbrella",
            "provider": "workday",
            "targetFingerprint": "sha256:exact-application-target",
            "observedAt": NOW,
        }
    )
    return database, lifecycle


def test_umbrella_happy_email_verification_resumes_exact_continuation_after_restart(
    tmp_path: Path,
) -> None:
    database, lifecycle = _lifecycle(tmp_path)
    lifecycle.begin_creation("account-umbrella", NOW)
    lifecycle.mark_created(
        "account-umbrella", "app-umbrella", NOW, verification_required=True
    )
    lifecycle.start_verification(
        {
            "challengeId": "challenge-happy",
            "accountId": "account-umbrella",
            "applicationId": "app-umbrella",
            "continuationId": "continuation-umbrella",
            "kind": "EMAIL_CODE",
            "observedAt": NOW,
            "expiresAt": "2026-09-16T12:10:00+00:00",
        }
    )
    lifecycle.mark_verification_ready(
        {
            "challengeId": "challenge-happy",
            "mailEventId": "mail-event-happy",
            "artifactDigest": "a" * 64,
            "observedAt": LATER,
        }
    )
    assert lifecycle.claim_verification("challenge-happy", LATER)["claimedNow"] is True

    restarted = ATSAccountLifecycle(database)
    restarted.requeue_claim("challenge-happy", LATER)
    assert restarted.claim_verification("challenge-happy", LATER)["claimedNow"] is True
    restarted.consume_verification("challenge-happy", LATER)
    assert restarted.mark_verified(
        "account-umbrella", "app-umbrella", LATER
    )["state"] == "VERIFIED"
    assert restarted.mark_continuation_ready(
        "continuation-umbrella", LATER
    )["state"] == "READY"
    assert restarted.consume_continuation(
        "continuation-umbrella", LATER
    )["state"] == "CONSUMED"
    assert restarted.mark_authenticated(
        "account-umbrella", "app-umbrella", LATER
    )["state"] == "AUTHENTICATED"


def test_umbrella_learning_promotes_only_verified_secretless_account_mechanics(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    teach = AccountTeachService(database)
    payload = {
        "applicationId": "app-umbrella",
        "siteOrigin": "https://wd5.myworkdayjobs.com",
        "componentFingerprint": "cfp-account-umbrella",
        "semanticType": "ATS_ACCOUNT_EMAIL_VERIFICATION_LINK",
        "atsFamily": "WORKDAY",
        "tenantKey": "example",
        "uiFingerprint": "account-ui-umbrella-v1",
        "actions": [{"type": "OPEN_VERIFICATION_LINK"}],
        "verifiedSuccess": True,
    }
    for index in range(3):
        lesson = dict(payload)
        lesson["observationId"] = f"learning-{index}"
        assert teach.capture(lesson)["containsSecretMaterial"] is False
        assert teach.drain(limit=1)["learned"] == 1
    promoted = teach.lookup_promoted(
        {
            "siteOrigin": payload["siteOrigin"],
            "componentFingerprint": payload["componentFingerprint"],
            "semanticType": payload["semanticType"],
            "atsFamily": payload["atsFamily"],
            "tenantKey": payload["tenantKey"],
            "uiFingerprint": payload["uiFingerprint"],
        }
    )
    assert promoted is not None
    assert promoted["state"] == "PROMOTED"
    assert promoted["verified_successes"] == 3


def test_umbrella_issue_security_challenge_preserves_application_without_bypass(
    tmp_path: Path,
) -> None:
    _database_instance, lifecycle = _lifecycle(tmp_path)
    lifecycle.begin_creation("account-umbrella", NOW)
    issue = lifecycle.security_issue(
        {
            "accountId": "account-umbrella",
            "applicationId": "app-umbrella",
            "continuationId": "continuation-umbrella",
            "challengeKind": "TOTP",
            "observedAt": LATER,
        }
    )
    assert issue["state"] == "NEEDS_USER_ACTION"
    assert issue["issue_code"] == "SECURITY_INTERVENTION_TOTP"
    assert issue["continuations"][0]["state"] == "ISSUE"


def test_umbrella_ambiguous_email_state_does_not_guess_or_advance_after_restart(
    tmp_path: Path,
) -> None:
    database, lifecycle = _lifecycle(tmp_path)
    lifecycle.begin_creation("account-umbrella", NOW)
    lifecycle.mark_created(
        "account-umbrella", "app-umbrella", NOW, verification_required=True
    )
    lifecycle.start_verification(
        {
            "challengeId": "challenge-ambiguous",
            "accountId": "account-umbrella",
            "applicationId": "app-umbrella",
            "continuationId": "continuation-umbrella",
            "kind": "EMAIL_LINK",
            "observedAt": NOW,
            "expiresAt": "2026-09-16T12:10:00+00:00",
        }
    )

    # Hunter has not produced a uniquely-correlated mail event. Apply therefore has
    # no artifact digest to consume and must preserve the continuation rather than
    # guessing which message/link belongs to this application.
    restarted = ATSAccountLifecycle(database)
    snapshot = restarted.snapshot("account-umbrella")
    challenge = snapshot["verificationChallenges"][0]
    continuation = snapshot["continuations"][0]
    assert challenge["state"] == "PENDING"
    assert challenge["mail_event_id"] is None
    assert challenge["artifact_digest"] is None
    assert continuation["state"] == "PENDING"
    assert snapshot["state"] == "VERIFICATION_PENDING"
