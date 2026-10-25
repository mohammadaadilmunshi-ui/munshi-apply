from __future__ import annotations

import json
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from munshi_apply_native import hosted_run_monitor as monitor

APPLICATION_ID = "application-d072cde0bb58c62eb4178af0b4645814"


def _setup_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    private_key = tmp_path / "test-ssh-key"
    private_key.write_text("synthetic test fixture\n")
    config = tmp_path / "hosted-monitor.json"
    config.write_text(json.dumps({
        "ssh_host": "munshi@159.195.244.16",
        "ssh_identity_file": str(private_key),
        "apply_container": "munshi-apply-production-apply-1",
    }))
    config.chmod(stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.setenv("MUNSHI_HOSTED_RUN_MONITOR_CONFIG", str(config))
    return config


def test_fails_closed_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MUNSHI_HOSTED_RUN_MONITOR_CONFIG", str(tmp_path / "missing.json")
    )
    with pytest.raises(ValueError, match="not configured"):
        monitor.get_hosted_run_status({"applicationId": APPLICATION_ID})


def test_rejects_untrusted_identity_and_config_permissions(tmp_path, monkeypatch):
    config = _setup_config(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="identity is invalid"):
        monitor.get_hosted_run_status({"applicationId": "--evil"})
    config.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        monitor.get_hosted_run_status({"applicationId": APPLICATION_ID})


def test_read_only_ssh_command_has_fixed_entry_and_no_mutations(tmp_path, monkeypatch):
    _setup_config(tmp_path, monkeypatch)
    captured = []

    def simulate_ssh(args, **kwargs):
        captured.append((args, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "source": "NETCUP_APPLY_DATABASE",
                "state": "FOUND",
                "application_id": APPLICATION_ID,
                "session": {
                    "session_id": "apply-session-test",
                    "state": "NEEDS_INPUT",
                },
            }),
        )

    monkeypatch.setattr(monitor.subprocess, "run", simulate_ssh)
    snapshot = monitor.get_hosted_run_status({"applicationId": APPLICATION_ID})
    assert snapshot["state"] == "FOUND"
    assert len(captured) == 1
    argv, options = captured[0]
    assert argv[:6] == [
        "/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
    ]
    assert "StrictHostKeyChecking=yes" in argv
    assert "docker exec" in argv[-1]
    assert "mode=ro" in argv[-1]
    assert "PRAGMA query_only=ON" in argv[-1]
    assert "INSERT" not in argv[-1]
    assert "UPDATE complete_application" not in argv[-1]
    assert options["timeout"] == 20
    assert options["capture_output"] is True


def test_native_bridge_returns_only_owner_selected_hosted_state(tmp_path, monkeypatch):
    _setup_config(tmp_path, monkeypatch)
    result = {
        "source": "NETCUP_APPLY_DATABASE",
        "state": "NOT_FOUND",
    }
    monkeypatch.setattr(
        monitor.subprocess,
        "run",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps(result)
        ),
    )
    assert monitor.get_hosted_run_status({"applicationId": APPLICATION_ID}) == result


def test_remote_status_script_reads_only_state_and_never_raw_answers(tmp_path):
    db_path = tmp_path / "apply.sqlite"
    db = sqlite3.connect(db_path)
    db.executescript("""
        CREATE TABLE complete_application_sessions
            (session_id TEXT,application_id TEXT,plan_id TEXT,state TEXT,
             checkpoint_id TEXT,updated_at TEXT);
        CREATE TABLE complete_application_prepare_jobs
            (job_id TEXT,session_id TEXT,state TEXT,attempt_count INT,
             max_attempts INT,updated_at TEXT);
        CREATE TABLE resolution_tasks
            (session_id TEXT,control_id TEXT,semantic_type TEXT,status TEXT,
             checkpoint_id TEXT,updated_at TEXT,secret_value TEXT);
        CREATE TABLE complete_application_execution_events
            (session_id TEXT,event_type TEXT,occurred_at TEXT,evidence_json TEXT);
        CREATE TABLE final_application_reviews (session_id TEXT);
        CREATE TABLE final_submit_commands (session_id TEXT);
        CREATE TABLE application_submission_receipts (session_id TEXT);
    """)
    db.execute(
        "INSERT INTO complete_application_sessions VALUES (?,?,?,?,?,?)",
        ("apply-session-1", APPLICATION_ID, "application-plan-1",
         "NEEDS_INPUT", "checkpoint-1", "2026-10-08T19:54:00Z"),
    )
    # A previous plan's durable session is history, not another active run.
    # Crescent has several such records in the production database.
    db.execute(
        "INSERT INTO complete_application_sessions VALUES (?,?,?,?,?,?)",
        ("apply-session-older", APPLICATION_ID, "application-plan-old",
         "FAILED_SAFELY", None, "2026-10-03T17:00:00Z"),
    )
    db.execute(
        "INSERT INTO complete_application_prepare_jobs VALUES (?,?,?,?,?,?)",
        ("prepare-job-1", "apply-session-1", "WAITING_INPUT", 2, 3,
         "2026-10-08T19:54:00Z"),
    )
    db.execute(
        "INSERT INTO resolution_tasks VALUES (?,?,?,?,?,?,?)",
        ("apply-session-1", "ctl-referral", "REFERRAL", "PENDING",
         "checkpoint-1", "2026-10-08T19:54:00Z", "do not show"),
    )
    db.execute(
        "INSERT INTO complete_application_execution_events VALUES (?,?,?,?)",
        ("apply-session-1", "FORM_PREPARED", "2026-10-08T19:54:00Z",
         '{"answer":"do not show"}'),
    )
    db.commit()
    db.close()
    code = monitor._REMOTE_READ_ONLY.replace(
        "/data/munshi-apply.sqlite", str(db_path)
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, APPLICATION_ID],
        check=True, capture_output=True, text=True,
    )
    status = json.loads(result.stdout)
    assert status["source"] == "NETCUP_APPLY_DATABASE"
    assert status["state"] == "FOUND"
    assert status["session"]["session_id"] == "apply-session-1"
    assert status["session"]["checkpoint_id"] == "checkpoint-1"
    assert status["prepare_job"]["attempt_count"] == 2
    assert status["pending_controls"][0]["semantic_type"] == "REFERRAL"
    assert status["events"][0]["event_type"] == "FORM_PREPARED"
    assert status["counts"]["employer_receipts"] == 0
    assert "do not show" not in result.stdout


def test_remote_status_script_fails_closed_on_tied_latest_sessions(tmp_path):
    db_path = tmp_path / "apply.sqlite"
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE complete_application_sessions "
            "(session_id TEXT,application_id TEXT,plan_id TEXT,state TEXT,"
            "checkpoint_id TEXT,updated_at TEXT)"
        )
        db.executemany(
            "INSERT INTO complete_application_sessions VALUES (?,?,?,?,?,?)",
            [
                ("apply-session-a", APPLICATION_ID, "plan-a",
                 "NEEDS_INPUT", "checkpoint-a", "2026-10-08T19:54:00Z"),
                ("apply-session-b", APPLICATION_ID, "plan-b",
                 "NEEDS_INPUT", "checkpoint-b", "2026-10-08T19:54:00Z"),
            ],
        )
    code = monitor._REMOTE_READ_ONLY.replace(
        "/data/munshi-apply.sqlite", str(db_path)
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, APPLICATION_ID],
        check=True, capture_output=True, text=True,
    )
    status = json.loads(result.stdout)
    assert status["state"] == "AMBIGUOUS"
    assert "session" not in status



def test_terminal_prepare_failure_overrides_stale_session_starting():
    snapshot = {
        "state": "FOUND",
        "session": {"session_id": "s1", "state": "SESSION_STARTING"},
        "prepare_job": {"state": "FAILED_SAFELY", "attempt_count": 3},
        "counts": {"employer_receipts": 0, "final_reviews": 0},
    }
    status = monitor.reconcile_readonly_hosted_state(snapshot)
    assert status["effective_state"] == "FAILED_SAFELY"
    assert status["session_state_mismatch"] is True
    assert status["submission_verified"] is False
    assert "do not automatically retry" in status["next_action"].lower()
    assert snapshot.get("effective_state") is None


def test_waiting_input_dominates_historical_session_state():
    status = monitor.reconcile_readonly_hosted_state({
        "state": "FOUND",
        "session": {"state": "PREPARING"},
        "prepare_job": {"state": "WAITING_INPUT"},
        "counts": {"final_reviews": 0},
    })
    assert status["effective_state"] == "NEEDS_INPUT"
    assert status["session_state_mismatch"] is True
    assert "must not submit" in status["next_action"]


def test_ready_for_review_requires_actual_frozen_review():
    missing = monitor.reconcile_readonly_hosted_state({
        "state": "FOUND", "session": {"state": "READY_FOR_REVIEW"},
        "prepare_job": {"state": "READY_FOR_REVIEW"},
        "counts": {"final_reviews": 0},
    })
    assert missing["effective_state"] == "REVIEW_NOT_FROZEN"
    ready = monitor.reconcile_readonly_hosted_state({
        "state": "FOUND", "session": {"state": "READY_FOR_REVIEW"},
        "prepare_job": {"state": "READY_FOR_REVIEW"},
        "counts": {"final_reviews": 1},
    })
    assert ready["effective_state"] == "READY_FOR_REVIEW"
    assert ready["submission_verified"] is False


def test_employer_receipt_counts_never_imply_verified_submission():
    status = monitor.reconcile_readonly_hosted_state({
        "state": "FOUND", "session": {"state": "SUBMITTING"},
        "prepare_job": None, "counts": {"employer_receipts": 1},
    })
    assert status["effective_state"] == "SUBMITTING"
    assert status["submission_verified"] is False
    assert monitor.reconcile_readonly_hosted_state({"state": "AMBIGUOUS"}) == {
        "state": "AMBIGUOUS"
    }
