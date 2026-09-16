from __future__ import annotations

from conftest import PRODUCTION_AUTHORITY_ENV
from test_application_plan_handoff_v2 import _consumer, _envelope, _signed
from test_complete_application_loop import FixtureBrowser, _seed_authority

from munshi_apply_native.account_continuation_bridge import (
    AccountContinuationBridge,
    canonical_continuation_target_fingerprint,
)
from munshi_apply_native.account_store import AccountStore
from munshi_apply_native.ats_account_lifecycle import ATSAccountLifecycle
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService

NOW = "2026-09-16T17:00:00+00:00"
LATER = "2026-09-16T17:01:00+00:00"


def test_verified_account_resumes_exact_application_then_submits_once(
    tmp_path,
    monkeypatch,
) -> None:
    for flag in (
        "MUNSHI_APPLY_LIVE_HANDOFF_ENABLED",
        "MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED",
        "MUNSHI_FINAL_REVIEW_ENABLED",
        "MUNSHI_FINAL_SUBMIT_ENABLED",
        PRODUCTION_AUTHORITY_ENV,
    ):
        monkeypatch.setenv(flag, "true")
    monkeypatch.setenv("MUNSHI_PRODUCTION_RECEIPT_HMAC_SECRET", "r" * 32)

    consumer, database = _consumer(tmp_path)
    body, headers = _signed(_envelope())
    assert consumer.accept(body, headers, now=1000).accepted

    service = CompleteApplicationLoopService(
        database,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    browser = FixtureBrowser()
    session = service.start_session(plan_id="application-plan-1")
    plan_record = service._plan(session.plan_id)  # noqa: SLF001 - acceptance fixture
    target_url = str(plan_record["plan"]["job"]["apply_url"])

    account_id = "account-exact-continuation"
    continuation_id = "continuation-exact-application"
    AccountStore(database).upsert(
        {
            "accountId": account_id,
            "employer": "Fixture Employer",
            "portalUrl": target_url,
            "email": "u_abcdefghijklmnop@mail.munshi.systems",
            "exists": False,
            "applicationId": session.application_id,
            "observedAt": NOW,
        }
    )

    lifecycle = ATSAccountLifecycle(database)
    lifecycle.provision(
        {
            "accountId": account_id,
            "provider": "greenhouse",
            "credentialRef": "credref:v1:abcdefghijklmnop",
            "mailAlias": "u_abcdefghijklmnop@mail.munshi.systems",
            "observedAt": NOW,
        }
    )
    lifecycle.bind_continuation(
        {
            "continuationId": continuation_id,
            "accountId": account_id,
            "applicationId": session.application_id,
            "executionSessionId": session.session_id,
            "provider": "greenhouse",
            "targetFingerprint": canonical_continuation_target_fingerprint(
                application_id=session.application_id,
                execution_session_id=session.session_id,
                provider="greenhouse",
                target_url=target_url,
            ),
            "observedAt": NOW,
        }
    )
    lifecycle.begin_creation(account_id, NOW)
    lifecycle.mark_created(
        account_id,
        session.application_id,
        NOW,
        verification_required=True,
    )
    lifecycle.start_verification(
        {
            "challengeId": "challenge-exact-application",
            "accountId": account_id,
            "applicationId": session.application_id,
            "continuationId": continuation_id,
            "kind": "EMAIL_CODE",
            "observedAt": NOW,
            "expiresAt": "2026-09-16T17:10:00+00:00",
        }
    )
    lifecycle.mark_verification_ready(
        {
            "challengeId": "challenge-exact-application",
            "mailEventId": "mail-event-exact-application",
            "artifactDigest": "a" * 64,
            "observedAt": LATER,
        }
    )
    assert lifecycle.claim_verification(
        "challenge-exact-application",
        LATER,
    )["claimedNow"] is True
    lifecycle.consume_verification("challenge-exact-application", LATER)
    assert lifecycle.mark_verified(
        account_id,
        session.application_id,
        LATER,
    )["state"] == "VERIFIED"
    assert lifecycle.mark_continuation_ready(
        continuation_id,
        LATER,
    )["state"] == "READY"

    # Simulate the hosted/native runtime being recreated after email verification.
    restarted_service = CompleteApplicationLoopService(
        database,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    resumed = AccountContinuationBridge(
        database,
        restarted_service,
    ).resume_verified(
        continuation_id=continuation_id,
        observed_at=LATER,
        adapter=browser,
    )
    assert resumed.application_id == session.application_id
    assert resumed.session_id == session.session_id
    assert resumed.state == "NEEDS_INPUT"

    snapshot = ATSAccountLifecycle(database).snapshot(account_id)
    assert snapshot["state"] == "AUTHENTICATED"
    assert snapshot["continuations"][0]["state"] == "CONSUMED"

    task = restarted_service.resolutions.list(
        application_id=session.application_id
    )[0]
    restarted_service.resolve_task(
        task_id=task.task_id,
        value="https://example.test/portfolio",
    )
    prepared = restarted_service.prepare_session(
        session_id=session.session_id,
        adapter=browser,
    )
    assert prepared.state == "READY_FOR_REVIEW"

    review = restarted_service.build_review(session_id=session.session_id)
    restarted_service.approve_review(review_id=review["review_id"])
    _seed_authority(
        (restarted_service, database, browser),
        review,
        session,
    )

    first = restarted_service.approve_and_submit(
        review_id=review["review_id"],
        idempotency_key="account-exact-submit-1",
        adapter=browser,
    )
    second = restarted_service.approve_and_submit(
        review_id=review["review_id"],
        idempotency_key="account-exact-submit-1",
        adapter=browser,
    )

    assert first["verification_status"] == "VERIFIED"
    assert second["receipt_id"] == first["receipt_id"]
    assert browser.calls == 1

    with database.connect() as connection:
        assert connection.execute(
            "SELECT state FROM complete_application_sessions WHERE session_id = ?",
            (session.session_id,),
        ).fetchone()[0] in {"SUBMITTED", "VERIFIED"}
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands WHERE application_id = ?",
            (session.application_id,),
        ).fetchone()[0] == 1
