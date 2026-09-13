from __future__ import annotations

from dataclasses import replace

import pytest
import test_complete_application_loop as fixtures

from munshi_apply_native.confirmation_evidence import (
    ConfirmationEvidenceService,
    ConfirmationMessage,
)

loop = fixtures.loop


def setup(loop):
    service, db, browser, session, review = fixtures.ready(loop)
    submit = browser.submit

    def observed(*, plan, review):
        result = submit(plan=plan, review=review)
        result["provider_application_id"] = "fixture-001"
        return result

    browser.submit = observed
    receipt = service.submit(review_id=review["review_id"], idempotency_key="one", adapter=browser)
    evidence = ConfirmationEvidenceService(db, tenant_id="tenant-a", user_id="member-a")
    message = ConfirmationMessage(
        "tenant-a",
        "member-a",
        "mailbox-1",
        "message-1",
        "GREENHOUSE",
        "fixture-001",
        "a" * 64,
        "2026-09-13T00:00:00Z",
    )
    return evidence, message, db, receipt, session


def test_confirmation_links_once_without_changing_lifecycle(loop):
    evidence, message, db, receipt, session = setup(loop)
    first = evidence.ingest(message)
    assert first["receipt_id"] == receipt["receipt_id"]
    assert evidence.ingest(message)["replayed"] is True
    with db.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM confirmation_email_evidence").fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT state FROM complete_application_sessions WHERE session_id=?",
                (session.session_id,),
            ).fetchone()[0]
            == "VERIFIED"
        )
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_other_owner_and_conflicting_replay_rejected(loop):
    evidence, message, _, _, _ = setup(loop)
    with pytest.raises(PermissionError):
        evidence.ingest(replace(message, user_id="other"))
    evidence.ingest(message)
    with pytest.raises(ValueError, match="conflicting"):
        evidence.ingest(replace(message, message_digest="b" * 64))


def test_unmatched_confirmation_does_not_create_evidence(loop):
    evidence, message, db, _, _ = setup(loop)
    assert (
        evidence.ingest(replace(message, provider_application_id="unknown"))["status"]
        == "UNMATCHED"
    )
    with db.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM confirmation_email_evidence").fetchone()[0]
            == 0
        )


def test_poll_disabled_does_not_call_provider(loop):
    evidence, _, _, _, _ = setup(loop)

    class NoCalls:
        def fetch_confirmations(self):
            raise AssertionError("Mailbox must not be contacted")

    with pytest.raises(RuntimeError, match="disabled"):
        evidence.poll(NoCalls())


def test_email_evidence_is_immutable(loop):
    evidence, message, db, _, _ = setup(loop)
    evidence.ingest(message)
    with pytest.raises(Exception, match="immutable"), db.connect() as connection:
        connection.execute("DELETE FROM confirmation_email_evidence")
