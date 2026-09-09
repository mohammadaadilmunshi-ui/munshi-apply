from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from munshi_apply_native.synthetic_submission_verification_v1 import (
    SyntheticSubmissionVerificationService,
)
from munshi_apply_native.synthetic_submit_execution_v1 import SyntheticSubmitExecutor
from test_synthetic_submit_command_inbox import SECRET, TARGET
from test_synthetic_submit_execution_v1 import FixtureSyntheticSubmitAdapter, _accepted


class FixtureIndependentVerifier:
    def __init__(self):
        self.calls = 0
        self.provider = "GREENHOUSE"
        self.job_id = "41"
        self.provider_application_id = "synthetic-application-001"
        self.provider_status = "received"
        self.lookup_confirmed = True
        self.observed_at = None
        self.crash = False
        self.malformed = False

    def observe_submission(self, *, plan, provider_application_id, target_url):
        self.calls += 1
        assert provider_application_id == "synthetic-application-001"
        assert target_url == TARGET
        assert str(plan["job"]["id"]) == "41"
        if self.crash:
            raise TimeoutError("synthetic provider lookup unavailable")
        if self.malformed:
            return None
        return {
            "synthetic": True,
            "verification_method": "SYNTHETIC_PROVIDER_LOOKUP",
            "observation_id": f"synthetic-provider-observation-{self.calls}",
            "provider": self.provider,
            "job_id": self.job_id,
            "provider_application_id": self.provider_application_id,
            "provider_status": self.provider_status,
            "lookup_confirmed": self.lookup_confirmed,
            "observed_at": self.observed_at
            or (datetime.now(UTC) + timedelta(seconds=2)).isoformat(),
            "provider_record_marker": "fixture-provider-record",
        }


def _submitted(tmp_path, monkeypatch, *, ambiguous=False):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED", "true")
    adapter = FixtureSyntheticSubmitAdapter(fields)
    adapter.ambiguous = ambiguous
    result = SyntheticSubmitExecutor(database, secret=SECRET).execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )
    return database, result


def _counts(database):
    with database.connect() as connection:
        return {
            "attempts": connection.execute(
                "SELECT COUNT(*) FROM synthetic_submission_verification_attempts"
            ).fetchone()[0],
            "receipts": connection.execute(
                "SELECT COUNT(*) FROM synthetic_submission_receipts"
            ).fetchone()[0],
            "legacy_receipts": connection.execute(
                "SELECT COUNT(*) FROM application_submission_receipts"
            ).fetchone()[0],
        }


def test_independent_verification_is_default_off(tmp_path, monkeypatch):
    database, submitted = _submitted(tmp_path, monkeypatch)
    assert submitted.state == "SUBMITTED"
    monkeypatch.delenv("MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED", raising=False)
    verifier = FixtureIndependentVerifier()
    result = SyntheticSubmissionVerificationService(database).verify(
        "synthetic-submit-command-1",
        verifier=verifier,
    )
    assert not result.verified
    assert result.state == "SUBMITTED"
    assert result.error == "synthetic submission verification disabled"
    assert verifier.calls == 0
    assert _counts(database) == {"attempts": 0, "receipts": 0, "legacy_receipts": 0}


def test_independent_lookup_verifies_once_and_creates_immutable_receipt(
    tmp_path,
    monkeypatch,
):
    database, submitted = _submitted(tmp_path, monkeypatch)
    assert submitted.state == "SUBMITTED"
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED", "true")
    verifier = FixtureIndependentVerifier()
    service = SyntheticSubmissionVerificationService(database)

    first = service.verify("synthetic-submit-command-1", verifier=verifier)
    second = service.verify("synthetic-submit-command-1", verifier=verifier)

    assert first.verified and first.state == "VERIFIED" and not first.replayed
    assert second.verified and second.state == "VERIFIED" and second.replayed
    assert second.receipt_id == first.receipt_id
    assert verifier.calls == 1
    assert _counts(database) == {"attempts": 1, "receipts": 1, "legacy_receipts": 0}

    with database.connect() as connection:
        assert connection.execute(
            "SELECT state FROM synthetic_submit_executions"
        ).fetchone()[0] == "SUBMITTED"
        assert connection.execute(
            "SELECT state FROM complete_application_sessions"
        ).fetchone()[0] == "VERIFIED"
        assert connection.execute(
            "SELECT status FROM applications"
        ).fetchone()[0] == "VERIFIED"
        receipt = connection.execute(
            """SELECT receipt_digest,execution_chain_digest,
                      verification_evidence_digest,verification_status
               FROM synthetic_submission_receipts"""
        ).fetchone()
        assert receipt["verification_status"] == "VERIFIED"
        assert len(receipt["receipt_digest"]) == 64
        assert len(receipt["execution_chain_digest"]) == 64
        assert len(receipt["verification_evidence_digest"]) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "LEVER"),
        ("job_id", "999"),
        ("provider_application_id", "another-application"),
        ("provider_status", "pending"),
        ("lookup_confirmed", False),
    ],
)
def test_mismatched_independent_evidence_never_verifies(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    database, submitted = _submitted(tmp_path, monkeypatch)
    assert submitted.state == "SUBMITTED"
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED", "true")
    verifier = FixtureIndependentVerifier()
    setattr(verifier, field, value)

    result = SyntheticSubmissionVerificationService(database).verify(
        "synthetic-submit-command-1",
        verifier=verifier,
    )

    assert not result.verified
    assert result.state == "SUBMITTED"
    assert verifier.calls == 1
    assert _counts(database)["attempts"] == 1
    assert _counts(database)["receipts"] == 0


@pytest.mark.parametrize(
    "observed_at",
    [
        "2000-01-01T00:00:00+00:00",
        "not-a-timestamp",
        "2026-01-01T00:00:00",
    ],
)
def test_verification_evidence_must_be_timestamped_after_submission(
    tmp_path,
    monkeypatch,
    observed_at,
):
    database, submitted = _submitted(tmp_path, monkeypatch)
    assert submitted.state == "SUBMITTED"
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED", "true")
    verifier = FixtureIndependentVerifier()
    verifier.observed_at = observed_at

    result = SyntheticSubmissionVerificationService(database).verify(
        "synthetic-submit-command-1",
        verifier=verifier,
    )

    assert not result.verified
    assert result.state == "SUBMITTED"
    assert verifier.calls == 1
    assert _counts(database)["attempts"] == 1
    assert _counts(database)["receipts"] == 0
    with database.connect() as connection:
        assert connection.execute(
            "SELECT state FROM complete_application_sessions"
        ).fetchone()[0] == "SUBMITTED"
        assert connection.execute(
            "SELECT status FROM applications"
        ).fetchone()[0] == "SUBMITTED"


def test_verifier_exception_and_malformed_result_fail_closed(tmp_path, monkeypatch):
    database, submitted = _submitted(tmp_path, monkeypatch)
    assert submitted.state == "SUBMITTED"
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED", "true")
    service = SyntheticSubmissionVerificationService(database)

    crashing = FixtureIndependentVerifier()
    crashing.crash = True
    assert not service.verify(
        "synthetic-submit-command-1",
        verifier=crashing,
    ).verified

    malformed = FixtureIndependentVerifier()
    malformed.malformed = True
    assert not service.verify(
        "synthetic-submit-command-1",
        verifier=malformed,
    ).verified

    assert _counts(database)["attempts"] == 2
    assert _counts(database)["receipts"] == 0


def test_submission_unverified_execution_cannot_be_promoted(tmp_path, monkeypatch):
    database, submitted = _submitted(tmp_path, monkeypatch, ambiguous=True)
    assert submitted.state == "SUBMISSION_UNVERIFIED"
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED", "true")
    verifier = FixtureIndependentVerifier()

    result = SyntheticSubmissionVerificationService(database).verify(
        "synthetic-submit-command-1",
        verifier=verifier,
    )

    assert not result.verified
    assert "Only a SUBMITTED synthetic execution" in (result.error or "")
    assert verifier.calls == 0
    assert _counts(database) == {"attempts": 0, "receipts": 0, "legacy_receipts": 0}


def test_verification_attempt_and_receipt_are_immutable(tmp_path, monkeypatch):
    database, submitted = _submitted(tmp_path, monkeypatch)
    assert submitted.state == "SUBMITTED"
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_VERIFICATION_ENABLED", "true")
    verifier = FixtureIndependentVerifier()
    assert SyntheticSubmissionVerificationService(database).verify(
        "synthetic-submit-command-1",
        verifier=verifier,
    ).verified

    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as connection:
            connection.execute(
                """UPDATE synthetic_submission_receipts
                   SET verification_status='VERIFIED'
                   WHERE command_id='synthetic-submit-command-1'"""
            )
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as connection:
            connection.execute(
                "DELETE FROM synthetic_submission_receipts"
            )
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as connection:
            connection.execute(
                "DELETE FROM synthetic_submission_verification_attempts"
            )
