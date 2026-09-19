from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.database import Database
from munshi_apply_native.hosted_account_orchestrator import (
    EMAIL_VERIFICATION,
    RESUME_APPLICATION,
    VERIFIED,
    HostedAccountOrchestrator,
)

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

REGISTER_URL = "https://careers.example.com/candidate/register"
VERIFY_URL = "https://careers.example.com/candidate/verify/browser-token"
NOW = "2026-09-19T02:00:00+00:00"


def _database(tmp_path: Path, application_id: str) -> Database:
    migrations = Path(__file__).resolve().parents[4] / "migrations"
    database = Database(tmp_path / "hosted-account-browser.sqlite", migrations)
    database.migrate()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications(
              application_id,job_id,status,resume_id,job_signal_score,
              submitted_at,created_at,updated_at
            ) VALUES(?,NULL,'DETECTED',NULL,NULL,NULL,?,?)
            """,
            (application_id, NOW, NOW),
        )
    return database


def _plan(application_id: str) -> dict[str, object]:
    return {
        "application_id": application_id,
        "plan_id": f"plan-{application_id}",
        "job": {
            "apply_url": REGISTER_URL,
            "job_url": REGISTER_URL,
            "company": "Browser Fixture",
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


class _Bridge:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.consumed: list[str] = []

    def mailbox_health(self, _plan: dict[str, object]) -> dict[str, object]:
        return {
            "ready": True,
            "mandatory": True,
            "relay_ready": True,
            "signing_ready": True,
            "encryption_ready": True,
        }

    def prepare_managed_account(
        self,
        _plan: dict[str, object],
        *,
        provider: str,
        account_scope: str,
        label: str,
    ) -> dict[str, str]:
        assert provider == "EXAMPLE"
        assert account_scope == "careers.example.com"
        assert label
        return {
            "account_id": f"account-browser-{self.mode}",
            "application_email": "u_browserfixture0001@mail.munshi.systems",
            "secret_ref": f"ats-secret://account-browser-{self.mode}/password",
        }

    def account_password(
        self,
        _plan: dict[str, object],
        *,
        account_id: str,
        secret_ref: str,
    ) -> str:
        assert account_id in secret_ref
        return "-".join(("Fixture", "Managed", "Credential", "1!"))

    def begin_mailbox_verification(
        self,
        _plan: dict[str, object],
        *,
        account_id: str,
        provider: str,
        expected_link_hosts: list[str],
        expected_sender_domains: list[str],
        ttl_minutes: int = 30,
    ) -> dict[str, object]:
        assert account_id.startswith("account-browser-")
        assert provider == "EXAMPLE"
        assert expected_link_hosts == ["careers.example.com"]
        assert expected_sender_domains == ["mail.example.com"]
        assert ttl_minutes == 30
        return {"request_id": f"request-{self.mode}", "mail_relay_ready": True}

    def claim_mailbox_verification(
        self,
        _plan: dict[str, object],
        *,
        request_id: str,
        account_id: str,
        expected_kind: str,
    ) -> dict[str, str]:
        assert request_id == f"request-{self.mode}"
        assert account_id == f"account-browser-{self.mode}"
        if self.mode == "code":
            assert expected_kind == "EMAIL_VERIFICATION_CODE"
            artifact = "482913"
        else:
            assert expected_kind == "EMAIL_VERIFICATION_LINK"
            artifact = VERIFY_URL
        return {
            "artifact_id": f"artifact-{self.mode}",
            "request_id": request_id,
            "inbound_id": f"mail-{self.mode}",
            "artifact_kind": expected_kind,
            "artifact_digest": hashlib.sha256(artifact.encode()).hexdigest(),
            "artifact": artifact,
            "lease_token": f"lease-{self.mode}",
        }

    def consume_mailbox_verification(
        self,
        _plan: dict[str, object],
        *,
        artifact_id: str,
        request_id: str,
        account_id: str,
        lease_token: str,
    ) -> dict[str, str]:
        assert request_id == f"request-{self.mode}"
        assert account_id == f"account-browser-{self.mode}"
        assert lease_token == f"lease-{self.mode}"
        self.consumed.append(artifact_id)
        return {
            "artifact_id": artifact_id,
            "request_id": request_id,
            "state": "CONSUMED",
        }

    def cancel_mailbox_verification(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, str]:
        raise AssertionError("Verification request must not be cancelled in this fixture")


def _registration_html(mode: str) -> str:
    if mode == "code":
        transition = """
          document.body.innerHTML =
            '<h1>Verify your email</h1>' +
            '<input id="code" autocomplete="one-time-code" />' +
            '<button id="verify-code">Verify</button>';
          document.querySelector("#verify-code").addEventListener("click", () => {
            const sameSession =
              sessionStorage.getItem("munshi-account-flow") === "same-context";
            const validCode = document.querySelector("#code").value === "482913";
            document.body.innerHTML =
              sameSession && validCode
                ? "<h1>Email verified. Your account is now active.</h1>"
                : "<h1>Verification failed.</h1>";
          });
        """
    else:
        transition = """
          document.body.innerHTML =
            "<h1>Check your email to verify your account</h1>";
        """

    page = """<!doctype html>
<html>
  <body>
    <h1>Create account</h1>
    <form id="create-account">
      <input type="email" name="email" />
      <input type="password" autocomplete="new-password" name="password" />
      <input type="password" autocomplete="new-password" name="confirm_password" />
      <button type="submit">Create account</button>
    </form>
    <script>
      sessionStorage.setItem("munshi-account-flow", "same-context");
      document.querySelector("#create-account").addEventListener("submit", (event) => {
        event.preventDefault();
        __TRANSITION__
      });
    </script>
  </body>
</html>"""
    return page.replace("__TRANSITION__", transition)


def _verification_link_html() -> str:
    return """<!doctype html>
<html>
  <body>
    <script>
      const sameSession =
        sessionStorage.getItem("munshi-account-flow") === "same-context";
      document.body.innerHTML = sameSession
        ? "<h1>Email verified. Your account is now active.</h1>"
        : "<h1>Verification failed.</h1>";
    </script>
  </body>
</html>"""


@pytest.mark.parametrize("mode", ["code", "link"])
def test_account_verification_stays_in_same_chromium_session(
    tmp_path: Path,
    mode: str,
) -> None:
    application_id = f"app-browser-{mode}"
    database = _database(tmp_path, application_id)
    bridge = _Bridge(mode)
    browser_path = resolve_browser_executable()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=browser_path,
        )
        context = browser.new_context()

        def handler(route: object) -> None:
            request = route.request
            if request.url == REGISTER_URL and request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=_registration_html(mode),
                )
                return
            if (
                mode == "link"
                and request.url == VERIFY_URL
                and request.method == "GET"
            ):
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=_verification_link_html(),
                )
                return
            route.abort()

        context.route("**/*", handler)
        page = context.new_page()
        page.goto(REGISTER_URL, wait_until="domcontentloaded")

        result = HostedAccountOrchestrator(
            database,
            plan=_plan(application_id),
            bridge=bridge,
            page=page,
            context=context,
            tenant_id="tenant-browser",
            user_id="user-browser",
            session_secret=b"browser-account-session-fixture-key",  # noqa: S106
            verification_timeout_seconds=5,
            poll_interval_seconds=0.05,
        ).run()

        assert result.state == RESUME_APPLICATION
        assert EMAIL_VERIFICATION in result.trace
        assert VERIFIED in result.trace
        assert result.trace[-1] == RESUME_APPLICATION
        assert bridge.consumed == [f"artifact-{mode}"]
        assert (
            page.evaluate("sessionStorage.getItem('munshi-account-flow')")
            == "same-context"
        )

        with database.connect() as connection:
            account = connection.execute(
                """
                SELECT state,verified_at,authenticated_at
                FROM ats_account_state
                WHERE account_id=?
                """,
                (f"account-browser-{mode}",),
            ).fetchone()
            persisted = connection.execute(
                """
                SELECT account_id,ciphertext,expires_at,invalidated_at
                FROM hosted_account_sessions
                WHERE tenant_id='tenant-browser'
                  AND user_id='user-browser'
                  AND scope_key='careers.example.com'
                """
            ).fetchone()

        assert account is not None
        assert account["state"] == "AUTHENTICATED"
        assert account["verified_at"]
        assert account["authenticated_at"]
        assert persisted is not None
        assert persisted["account_id"] == f"account-browser-{mode}"
        assert bytes(persisted["ciphertext"])
        assert persisted["expires_at"]
        assert persisted["invalidated_at"] is None

        context.close()
        browser.close()
