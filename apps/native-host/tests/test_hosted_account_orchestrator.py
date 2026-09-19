from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.account_store import AccountStore
from munshi_apply_native.ats_account_lifecycle import ATSAccountLifecycle
from munshi_apply_native.database import Database
from munshi_apply_native.hosted_account_orchestrator import (
    HostedAccountIssue,
    HostedAccountOrchestrator,
)


NOW = "2026-09-18T20:00:00+00:00"


def _database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "orchestrator.sqlite", migrations)
    database.migrate()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications(
              application_id,job_id,status,resume_id,job_signal_score,
              submitted_at,created_at,updated_at
            ) VALUES('app-1',NULL,'DETECTED',NULL,NULL,NULL,?,?)
            """,
            (NOW, NOW),
        )
    AccountStore(database).upsert(
        {
            "accountId": "account-1",
            "employer": "Example",
            "portalUrl": "https://careers.example.com/candidate/login",
            "email": "u_abcdefghijklmnop@mail.munshi.systems",
            "exists": True,
            "applicationId": "app-1",
            "observedAt": NOW,
        }
    )
    ATSAccountLifecycle(database).provision(
        {
            "accountId": "account-1",
            "provider": "example",
            "credentialRef": "ats-secret://account-1/password",
            "mailAlias": "u_abcdefghijklmnop@mail.munshi.systems",
            "observedAt": NOW,
        }
    )
    return database


class _Bridge:
    tenant_id = "tenant-1"
    user_id = "user-1"
    secret = b"h" * 32  # noqa: S105 - deterministic test bridge key, not a real secret

    def mailbox_health(self, _plan):
        return {
            "ready": False,
            "mandatory": True,
            "relay_ready": False,
            "signing_ready": True,
            "encryption_ready": True,
        }


def _plan():
    return {
        "application_id": "app-1",
        "plan_id": "plan-1",
        "job": {
            "apply_url": "https://careers.example.com/candidate/login",
            "job_url": "https://careers.example.com/candidate/login",
            "company": "Example",
        },
        "provider_policy": {
            "provider": "EXAMPLE",
            "allowed_hosts": ["careers.example.com"],
            "mailbox_verification": {
                "sender_domains": ["mail.example.com"],
                "link_hosts": ["careers.example.com"],
            },
        },
    }


def test_mandatory_mailbox_failure_durably_becomes_issue(tmp_path: Path) -> None:
    database = _database(tmp_path)
    orchestrator = HostedAccountOrchestrator(
        database,
        plan=_plan(),
        bridge=_Bridge(),
        page=object(),
        context=object(),
        verification_timeout_seconds=5,
        poll_interval_seconds=0.1,
    )
    orchestrator._account_required = lambda: True  # type: ignore[method-assign]
    orchestrator._is_create = lambda: False  # type: ignore[method-assign]

    with pytest.raises(HostedAccountIssue) as raised:
        orchestrator.run()
    assert raised.value.issue_code == "MAILBOX_RUNTIME_UNAVAILABLE"

    snapshot = ATSAccountLifecycle(database).snapshot("account-1")
    assert snapshot["state"] == "FAILED_SAFE"
    assert snapshot["issue_code"] == "MAILBOX_RUNTIME_UNAVAILABLE"
    assert snapshot["continuations"]
    assert snapshot["continuations"][0]["state"] == "ISSUE"
    assert snapshot["continuations"][0]["issue_code"] == "MAILBOX_RUNTIME_UNAVAILABLE"

    with database.connect() as connection:
        events = connection.execute(
            """
            SELECT state,issue_code
            FROM hosted_account_orchestration_events
            WHERE application_id='app-1'
            ORDER BY occurred_at,event_id
            """
        ).fetchall()
    assert any(
        str(row["state"]) == "ISSUE"
        and str(row["issue_code"]) == "MAILBOX_RUNTIME_UNAVAILABLE"
        for row in events
    )


class _Page:
    def __init__(self) -> None:
        self.url = "https://careers.example.com/candidate/verify"

    def goto(self, url: str, **_kwargs):
        self.url = url
        return None

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


def _orchestrator_for_direct_checks(tmp_path: Path, plan=None) -> HostedAccountOrchestrator:
    return HostedAccountOrchestrator(
        _database(tmp_path),
        plan=plan or _plan(),
        bridge=_Bridge(),
        page=_Page(),
        context=object(),
        verification_timeout_seconds=5,
        poll_interval_seconds=0.1,
    )


def test_email_verification_link_requires_positive_confirmation(tmp_path: Path) -> None:
    orchestrator = _orchestrator_for_direct_checks(tmp_path)
    orchestrator._text = (  # type: ignore[method-assign]
        lambda: "Email verified. Your account is now active."
    )
    orchestrator._visible = lambda _selectors: None  # type: ignore[method-assign]
    assert orchestrator._apply_verification(
        "EMAIL_VERIFICATION_LINK",
        "https://careers.example.com/candidate/verify/token",
    ) is True


def test_email_verification_link_rejects_navigation_only_or_failure_page(tmp_path: Path) -> None:
    orchestrator = _orchestrator_for_direct_checks(tmp_path)
    orchestrator._visible = lambda _selectors: None  # type: ignore[method-assign]
    orchestrator._text = lambda: "Welcome to the candidate portal."  # type: ignore[method-assign]
    assert orchestrator._apply_verification(
        "EMAIL_VERIFICATION_LINK",
        "https://careers.example.com/candidate/verify/token",
    ) is False

    orchestrator._text = (  # type: ignore[method-assign]
        lambda: "This verification link has expired."
    )
    assert orchestrator._apply_verification(
        "EMAIL_VERIFICATION_LINK",
        "https://careers.example.com/candidate/verify/token",
    ) is False


def test_username_policy_can_use_managed_email_local_part(tmp_path: Path) -> None:
    plan = _plan()
    plan["provider_policy"]["account_identity"] = {
        "username_policy": "EMAIL_LOCAL_PART"
    }
    orchestrator = _orchestrator_for_direct_checks(tmp_path, plan=plan)
    assert (
        orchestrator._login_identifier(
            "u_abcdefghijklmnop@mail.munshi.systems"
        )
        == "u_abcdefghijklmnop"
    )
