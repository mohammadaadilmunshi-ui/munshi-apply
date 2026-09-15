from __future__ import annotations

import hashlib
import json

import pytest
from conftest import (
    PRODUCTION_AUTHORITY_ENV,
    build_authority_envelope,
    seed_production_authority,
    sign_authority_envelope,
)
from test_application_plan_handoff_v2 import _consumer, _envelope, _signed

from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService


class FixtureBrowser:
    """Deterministic orchestration fixture; actual DOM tests are separate."""

    def __init__(self):
        self.calls = 0
        self.changed = False
        self.blocker = None
        self.ambiguous = False
        self.generic_confirmation = False
        self.crash = False
        self.last_form = None

    def inspect_job(self, *, plan):
        return {
            "provider": "GREENHOUSE",
            "job_id": str(plan["job"]["id"]),
            "current_url": plan["job"]["apply_url"],
            "page_id": "fixture",
            "page_fingerprint": "fixture-form",
            "security_checkpoint": self.blocker,
        }

    def prepare_form(self, *, plan, checkpoint, resolved_values):
        value = resolved_values.get("portfolio")
        fields = [
            {"question_key": "portfolio", "display_value": value, "sensitivity_class": "NORMAL"}
        ]
        self.last_form = {
            **self.inspect_job(plan=plan),
            "resume_uploaded": True,
            "resume_sha256": plan["resume"]["artifact_sha256"],
            "completed_control_ids": ["resume"] + (["portfolio"] if value else []),
            "pending_control_ids": [] if value else ["portfolio"],
            "required_fields": 1,
            "completed_required_fields": int(bool(value)),
            "form_digest": hashlib.sha256(json.dumps(fields).encode()).hexdigest(),
            "review_fields": fields,
            "validation_errors": [],
            "unresolved": []
            if value
            else [
                {
                    "question_key": "portfolio",
                    "control_id": "portfolio",
                    "question": "Portfolio URL",
                    "semantic_type": "UNKNOWN",
                    "reason": "No confirmed answer",
                    "sensitivity": "NORMAL",
                }
            ],
        }
        return self.last_form

    def inspect_submission(self, *, plan):
        return {
            **self.last_form,
            **self.inspect_job(plan=plan),
            "form_digest": "0" * 64 if self.changed else self.last_form["form_digest"],
            "supported": True,
            "plan_current": True,
        }

    def submit(self, *, plan, review):
        self.calls += 1
        if self.crash:
            raise TimeoutError("fixture response lost after action")
        return {
            "action_executed": True,
            "verification_status": "VERIFIED",
            "submission_url": plan["job"]["apply_url"],
            "success_evidence": (
                {"url_transition": "somewhere"}
                if self.ambiguous
                else (
                    {
                        "completion_marker": "application-submitted",
                        "confirmation_message": "Thank you for applying",
                        "provider": "GREENHOUSE",
                        "job_id": str(plan["job"]["id"]),
                    }
                    if self.generic_confirmation
                    else {
                        "completion_marker": "application-submitted",
                        "provider": "GREENHOUSE",
                        "job_id": str(plan["job"]["id"]),
                        "provider_application_id": "fixture-001",
                        "response_status": 201,
                        "response_url": plan["job"]["apply_url"],
                        "submit_action": plan["job"]["apply_url"],
                        "submit_method": "POST",
                        "submission_response_marker": "provider-json-application-id",
                    }
                )
            ),
        }


@pytest.fixture
def loop(tmp_path, monkeypatch):
    for flag in (
        "MUNSHI_APPLY_LIVE_HANDOFF_ENABLED",
        "MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED",
        "MUNSHI_FINAL_REVIEW_ENABLED",
        "MUNSHI_FINAL_SUBMIT_ENABLED",
        PRODUCTION_AUTHORITY_ENV,
    ):
        monkeypatch.setenv(flag, "true")
    consumer, db = _consumer(tmp_path)
    body, headers = _signed(_envelope())
    assert consumer.accept(body, headers, now=1000).accepted
    service = CompleteApplicationLoopService(db, tenant_id="tenant-a", user_id="member-a")
    return service, db, FixtureBrowser()


def ready(loop):
    service, db, browser = loop
    session = service.start_session(plan_id="application-plan-1")
    pending = service.prepare_session(session_id=session.session_id, adapter=browser)
    assert pending.state == "NEEDS_INPUT"
    tasks = service.resolutions.list(application_id=session.application_id)
    assert len(tasks) == 1
    service.resolve_task(task_id=tasks[0].task_id, value="https://example.test/portfolio")
    prepared = service.prepare_session(session_id=session.session_id, adapter=browser)
    assert prepared.state == "READY_FOR_REVIEW"
    review = service.build_review(session_id=session.session_id)
    service.approve_review(review_id=review["review_id"])
    return service, db, browser, session, review


def _seed_authority(loop, review, session):
    """Seed a CLAIMED production authority for the given review+session.

    Reads the durable plan/session/checkpoint fields so the envelope binds
    exactly to Apply's current state.
    """
    service, db, browser = loop
    plan_record = service._plan("application-plan-1")  # noqa: SLF001 - test fixture
    form_digest = (
        browser.last_form["form_digest"]
        if browser.last_form
        else "f" * 64
    )
    envelope = build_authority_envelope(
        authorization_id="auth-test-1",
        application_id=session.application_id,
        plan_id=session.plan_id,
        session_id=session.session_id,
        review_id=review["review_id"],
        approval_id="review-approval-test-1",
        plan_digest=plan_record["plan_digest"],
        review_digest=review["review_digest"],
        approval_digest=hashlib.sha256(b"approval").hexdigest(),
        prepared_package_digest=hashlib.sha256(b"prepared").hexdigest(),
        browser_form_digest=form_digest,
        resume_sha256=plan_record["plan"]["resume"]["artifact_sha256"],
        cover_letter_sha256=None,
        target_url=plan_record["plan"]["job"]["apply_url"],
        checkpoint_id="checkpoint-1",
    )
    with db.connect() as connection:
        session_row = connection.execute(
            "SELECT checkpoint_id, browser_form_digest, current_url "
            "FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
    envelope["checkpoint_id"] = str(session_row["checkpoint_id"])
    envelope["browser_form_digest"] = str(session_row["browser_form_digest"])
    envelope["target_url"] = str(session_row["current_url"])
    envelope = sign_authority_envelope(envelope)
    return seed_production_authority(
        database=db, service=service, envelope=envelope, review_id=review["review_id"]
    )


def test_one_customer_approval_freezes_and_submits_once(loop):
    service, _, browser = loop
    session = service.start_session(plan_id="application-plan-1")
    pending = service.prepare_session(session_id=session.session_id, adapter=browser)
    assert pending.state == "NEEDS_INPUT"
    task = service.resolutions.list(application_id=session.application_id)[0]
    service.resolve_task(task_id=task.task_id, value="https://example.test/portfolio")
    prepared = service.prepare_session(session_id=session.session_id, adapter=browser)
    assert prepared.state == "READY_FOR_REVIEW"
    review = service.build_review(session_id=session.session_id)
    # approve_review transitions the session to READY_TO_SUBMIT before we
    # seed the canonical authority. The seed requires READY_TO_SUBMIT.
    service.approve_review(review_id=review["review_id"])
    _seed_authority(loop, review, session)

    first = service.approve_and_submit(
        review_id=review["review_id"],
        idempotency_key="single-approval-1",
        adapter=browser,
    )
    second = service.approve_and_submit(
        review_id=review["review_id"],
        idempotency_key="single-approval-1",
        adapter=browser,
    )

    assert first["verification_status"] == "VERIFIED"
    assert second["receipt_id"] == first["receipt_id"]
    assert browser.calls == 1

def test_checkpoint_resolution_review_and_submit_once(loop):
    service, db, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    first = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    second = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    assert first["verification_status"] == "VERIFIED"
    assert second["receipt_id"] == first["receipt_id"]
    assert browser.calls == 1
    with db.connect() as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_browser_change_after_approval_prevents_submit(loop):
    service, _, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    browser.changed = True
    with pytest.raises((ValueError, RuntimeError), match="(?i)form|review|changed"):
        service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 0


def test_security_checkpoint_after_approval_prevents_submit(loop):
    service, _, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    browser.blocker = "MFA"
    with pytest.raises((ValueError, RuntimeError), match="(?i)security|blocked"):
        service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 0


def test_url_transition_alone_is_not_verification(loop):
    service, _, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    browser.ambiguous = True
    receipt = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    assert receipt["verification_status"] == "SUBMISSION_UNVERIFIED"


def test_generic_confirmation_alone_is_not_verification(loop):
    service, _, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    browser.generic_confirmation = True
    receipt = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    assert receipt["verification_status"] == "SUBMISSION_UNVERIFIED"


def test_lost_response_is_durable_ambiguous_outcome(loop):
    service, _, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    browser.crash = True
    receipt = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    assert receipt["verification_status"] == "SUBMISSION_UNVERIFIED"
    service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 1


def test_receipt_binds_resolved_answer_and_final_event(loop):
    service, db, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    receipt = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    snapshot = receipt["receipt"]
    assert snapshot["answers_snapshot"][0]["display_value"] == "https://example.test/portfolio"
    assert snapshot["resume_version_id"] == "resume-v5-1"
    assert any(e["event_type"] == "SUBMISSION_OBSERVED" for e in snapshot["execution_events"])
    with db.connect() as conn, pytest.raises(Exception, match="immutable"):
        conn.execute("DELETE FROM application_submission_receipts")


def test_default_off_submit_never_calls_adapter(loop, monkeypatch):
    service, _, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    monkeypatch.delenv("MUNSHI_FINAL_SUBMIT_ENABLED")
    with pytest.raises(RuntimeError, match="disabled"):
        service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 0


def test_production_authority_enabled_without_a_claimed_authority_blocks_submit(loop):
    """§6: even with BOTH gates on, no claimed authority means no boundary crossing.

    The inbox is keyless and constructed on demand, so a missing wiring cannot be
    the security property. What must hold is that the irreversible adapter call is
    unreachable unless a canonical authority has actually been claimed for the
    session.
    """
    service, _, browser, session, review = ready(loop)
    from munshi_apply_native.submit_authority_inbox_v1 import production_authority_enabled

    assert production_authority_enabled() is True
    with pytest.raises(RuntimeError, match="Canonical submit authority"):
        service.submit(
            review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
        )
    assert browser.calls == 0


def test_production_authority_default_off(monkeypatch):
    """The §6 canonical-authority gate must remain default-off."""
    monkeypatch.delenv("MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED", raising=False)
    from munshi_apply_native.submit_authority_inbox_v1 import production_authority_enabled
    assert production_authority_enabled() is False


def test_production_authority_default_off_blocks_submit(loop, monkeypatch):
    """§6: with the canonical gate off, the irreversible boundary is unreachable."""
    service, _, browser, session, review = ready(loop)
    monkeypatch.delenv(PRODUCTION_AUTHORITY_ENV, raising=False)
    with pytest.raises(RuntimeError, match="Canonical submit authority is disabled"):
        service.submit(
            review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
        )
    assert browser.calls == 0


def test_submit_rebuilds_keyless_inbox_on_fresh_instance(loop):
    """Claimed authority must be honourable without a previously bound inbox.

    _loop_service yields a fresh service per request, so the instance that
    receives a delivery is never the instance that submits. The inbox is keyless
    and stateless, so constructing it on demand grants nothing extra.
    """
    service, _, browser, session, review = ready(loop)
    _seed_authority(loop, review, session)
    service._authority_inbox = None  # noqa: SLF001 - simulate a fresh instance
    receipt = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    assert browser.calls == 1
    assert "verification_status" in receipt
