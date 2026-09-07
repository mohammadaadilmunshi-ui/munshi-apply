from __future__ import annotations

import hashlib
import json

import pytest
from test_application_plan_handoff_v2 import _consumer, _envelope, _signed

from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService


class FixtureBrowser:
    """Deterministic orchestration fixture; actual DOM tests are separate."""

    def __init__(self):
        self.calls = 0
        self.changed = False
        self.blocker = None
        self.ambiguous = False
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
                else {
                    "completion_marker": "application-submitted",
                    "provider": "GREENHOUSE",
                    "job_id": str(plan["job"]["id"]),
                    "provider_application_id": "fixture-001",
                }
            ),
        }


@pytest.fixture
def loop(tmp_path, monkeypatch):
    for flag in (
        "MUNSHI_APPLY_LIVE_HANDOFF_ENABLED",
        "MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED",
        "MUNSHI_FINAL_REVIEW_ENABLED",
        "MUNSHI_FINAL_SUBMIT_ENABLED",
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


def test_checkpoint_resolution_review_and_submit_once(loop):
    service, db, browser, session, review = ready(loop)
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
    service, _, browser, _, review = ready(loop)
    browser.changed = True
    with pytest.raises((ValueError, RuntimeError), match="(?i)form|review|changed"):
        service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 0


def test_security_checkpoint_after_approval_prevents_submit(loop):
    service, _, browser, _, review = ready(loop)
    browser.blocker = "MFA"
    with pytest.raises((ValueError, RuntimeError), match="(?i)security|blocked"):
        service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 0


def test_url_transition_alone_is_not_verification(loop):
    service, _, browser, _, review = ready(loop)
    browser.ambiguous = True
    receipt = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    assert receipt["verification_status"] == "SUBMISSION_UNVERIFIED"


def test_lost_response_is_durable_ambiguous_outcome(loop):
    service, _, browser, _, review = ready(loop)
    browser.crash = True
    receipt = service.submit(
        review_id=review["review_id"], idempotency_key="submit-1", adapter=browser
    )
    assert receipt["verification_status"] == "SUBMISSION_UNVERIFIED"
    service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 1


def test_receipt_binds_resolved_answer_and_final_event(loop):
    service, db, browser, _, review = ready(loop)
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
    service, _, browser, _, review = ready(loop)
    monkeypatch.delenv("MUNSHI_FINAL_SUBMIT_ENABLED")
    with pytest.raises(RuntimeError, match="disabled"):
        service.submit(review_id=review["review_id"], idempotency_key="submit-1", adapter=browser)
    assert browser.calls == 0
