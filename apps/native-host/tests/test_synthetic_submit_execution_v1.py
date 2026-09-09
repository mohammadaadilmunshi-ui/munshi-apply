from __future__ import annotations

import sqlite3

import pytest

from munshi_apply_native.synthetic_submit_command_inbox import SyntheticSubmitCommandInbox
from munshi_apply_native.synthetic_submit_execution_v1 import SyntheticSubmitExecutor
from test_synthetic_submit_command_inbox import SECRET, TARGET, _command, _ready


class FixtureSyntheticSubmitAdapter:
    def __init__(self, fields):
        self.fields = fields
        self.inspect_calls = 0
        self.submit_calls = 0
        self.drift_form = False
        self.blocked = False
        self.crash = False
        self.ambiguous = False
        self.malformed = False

    def inspect_submission(self, *, plan):
        self.inspect_calls += 1
        return {
            "provider": "GREENHOUSE",
            "job_id": str(plan["job"]["id"]),
            "current_url": TARGET,
            "form_digest": "0" * 64 if self.drift_form else self.fields["form"],
            "supported": True,
            "plan_current": True,
            "security_checkpoint": None,
            "resume_uploaded": True,
            "resume_sha256": plan["resume"]["artifact_sha256"],
            "required_fields": 2,
            "completed_required_fields": 2,
            "unresolved": [],
            "validation_errors": [],
        }

    def submit(self, *, plan, review):
        self.submit_calls += 1
        assert review["synthetic"] is True
        assert review["submission_authority"] is True
        assert review["destination_url"] == TARGET
        assert review["browser_verification"]["form_digest"] == self.fields["form"]

        if self.crash:
            raise TimeoutError("synthetic response lost after submit action")
        if self.malformed:
            return None
        if self.blocked:
            return {
                "action_executed": False,
                "verification_status": "BLOCKED",
            }
        if self.ambiguous:
            return {
                "action_executed": True,
                "verification_status": "VERIFIED",
                "submission_url": TARGET,
                "success_evidence": {
                    "provider": "GREENHOUSE",
                    "job_id": str(plan["job"]["id"]),
                    "completion_marker": "synthetic-confirmation",
                },
            }
        return {
            "action_executed": True,
            "verification_status": "VERIFIED",
            "submission_url": TARGET,
            "provider_application_id": "synthetic-application-001",
            "success_evidence": {
                "provider": "GREENHOUSE",
                "job_id": str(plan["job"]["id"]),
                "provider_application_id": "synthetic-application-001",
                "response_status": 201,
                "response_url": TARGET,
                "submit_action": TARGET,
                "submit_method": "POST",
                "completion_marker": "synthetic-application-submitted",
                "submission_response_marker": "synthetic-provider-application-id",
            },
        }


def _accepted(tmp_path, monkeypatch):
    database, plan, fields = _ready(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED",
        "true",
    )
    inbox = SyntheticSubmitCommandInbox(database, secret=SECRET)
    body, body_sha256, signature = _command(plan, fields)
    accepted = inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature,
        now=1100,
    )
    assert accepted.accepted
    return database, fields, inbox


def _counts(database):
    with database.connect() as connection:
        return {
            "claims": connection.execute(
                "SELECT COUNT(*) FROM synthetic_submit_command_claims"
            ).fetchone()[0],
            "executions": connection.execute(
                "SELECT COUNT(*) FROM synthetic_submit_executions"
            ).fetchone()[0],
            "legacy_commands": connection.execute(
                "SELECT COUNT(*) FROM final_submit_commands"
            ).fetchone()[0],
            "receipts": connection.execute(
                "SELECT COUNT(*) FROM application_submission_receipts"
            ).fetchone()[0],
        }


def test_execution_is_default_off_and_does_not_claim(tmp_path, monkeypatch):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.delenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        raising=False,
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    executor = SyntheticSubmitExecutor(database, secret=SECRET)

    result = executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )

    assert result.state == "READY_TO_SUBMIT"
    assert result.error == "synthetic submit execution disabled"
    assert adapter.inspect_calls == 0
    assert adapter.submit_calls == 0
    assert _counts(database) == {
        "claims": 0,
        "executions": 0,
        "legacy_commands": 0,
        "receipts": 0,
    }


def test_correlated_synthetic_action_is_submitted_once_not_verified(
    tmp_path,
    monkeypatch,
):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    executor = SyntheticSubmitExecutor(database, secret=SECRET)

    first = executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )
    second = executor.execute(
        "synthetic-submit-command-1",
        now=1102,
        adapter=adapter,
    )

    assert first.state == "SUBMITTED"
    assert not first.replayed
    assert first.provider_application_id == "synthetic-application-001"
    assert second.state == "SUBMITTED"
    assert second.replayed
    assert adapter.inspect_calls == 1
    assert adapter.submit_calls == 1
    assert _counts(database) == {
        "claims": 1,
        "executions": 1,
        "legacy_commands": 0,
        "receipts": 0,
    }

    with database.connect() as connection:
        session = connection.execute(
            "SELECT state FROM complete_application_sessions"
        ).fetchone()
        application = connection.execute(
            "SELECT status,submitted_at FROM applications"
        ).fetchone()
        execution = connection.execute(
            "SELECT state,result_digest FROM synthetic_submit_executions"
        ).fetchone()
        assert session["state"] == "SUBMITTED"
        assert application["status"] == "SUBMITTED"
        assert application["submitted_at"] is not None
        assert execution["state"] == "SUBMITTED"
        assert len(execution["result_digest"]) == 64


def test_pre_submit_browser_drift_fails_safely_without_submit(
    tmp_path,
    monkeypatch,
):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    adapter.drift_form = True
    executor = SyntheticSubmitExecutor(database, secret=SECRET)

    result = executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )

    assert result.state == "FAILED_SAFELY"
    assert result.action_executed is False
    assert adapter.inspect_calls == 1
    assert adapter.submit_calls == 0


def test_ambiguous_submit_exception_is_never_retried(tmp_path, monkeypatch):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    adapter.crash = True
    executor = SyntheticSubmitExecutor(database, secret=SECRET)

    first = executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )
    second = executor.execute(
        "synthetic-submit-command-1",
        now=1102,
        adapter=adapter,
    )

    assert first.state == "SUBMISSION_UNVERIFIED"
    assert first.action_executed is None
    assert second.state == "SUBMISSION_UNVERIFIED"
    assert second.replayed
    assert adapter.submit_calls == 1
    assert _counts(database)["receipts"] == 0


def test_malformed_submit_result_is_ambiguous_and_never_retried(
    tmp_path,
    monkeypatch,
):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    adapter.malformed = True
    executor = SyntheticSubmitExecutor(database, secret=SECRET)

    first = executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )
    second = executor.execute(
        "synthetic-submit-command-1",
        now=1102,
        adapter=adapter,
    )

    assert first.state == "SUBMISSION_UNVERIFIED"
    assert first.action_executed is None
    assert second.state == "SUBMISSION_UNVERIFIED"
    assert second.replayed
    assert adapter.submit_calls == 1
    assert _counts(database)["receipts"] == 0


def test_uncorrelated_action_is_submission_unverified(tmp_path, monkeypatch):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    adapter.ambiguous = True
    executor = SyntheticSubmitExecutor(database, secret=SECRET)

    result = executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )

    assert result.state == "SUBMISSION_UNVERIFIED"
    assert result.action_executed is True
    assert _counts(database)["receipts"] == 0


def test_blocked_before_action_stays_blocked(tmp_path, monkeypatch):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    adapter.blocked = True
    executor = SyntheticSubmitExecutor(database, secret=SECRET)

    result = executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    )

    assert result.state == "BLOCKED"
    assert result.action_executed is False
    assert adapter.submit_calls == 1
    assert _counts(database)["receipts"] == 0


def test_phase_g_claim_without_execution_fails_closed(tmp_path, monkeypatch):
    database, fields, inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    claim = inbox.claim("synthetic-submit-command-1", now=1101)
    assert claim.claimed

    adapter = FixtureSyntheticSubmitAdapter(fields)
    executor = SyntheticSubmitExecutor(database, secret=SECRET)
    result = executor.execute(
        "synthetic-submit-command-1",
        now=1102,
        adapter=adapter,
    )

    assert result.state == "READY_TO_SUBMIT"
    assert "claim exists without execution" in (result.error or "")
    assert adapter.inspect_calls == 0
    assert adapter.submit_calls == 0


def test_terminal_execution_ledger_is_immutable(tmp_path, monkeypatch):
    database, fields, _inbox = _accepted(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "MUNSHI_APPLY_SYNTHETIC_SUBMIT_EXECUTION_ENABLED",
        "true",
    )
    adapter = FixtureSyntheticSubmitAdapter(fields)
    executor = SyntheticSubmitExecutor(database, secret=SECRET)
    assert executor.execute(
        "synthetic-submit-command-1",
        now=1101,
        adapter=adapter,
    ).state == "SUBMITTED"

    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as connection:
            connection.execute(
                """UPDATE synthetic_submit_executions
                   SET state='SUBMISSION_UNVERIFIED'
                   WHERE command_id='synthetic-submit-command-1'"""
            )

    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as connection:
            connection.execute(
                """DELETE FROM synthetic_submit_executions
                   WHERE command_id='synthetic-submit-command-1'"""
            )
