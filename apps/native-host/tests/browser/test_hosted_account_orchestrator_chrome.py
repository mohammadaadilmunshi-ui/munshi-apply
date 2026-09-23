from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munshi_apply_native.account_store import AccountStore
from munshi_apply_native.ats_account_lifecycle import ATSAccountLifecycle
from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.database import Database
from munshi_apply_native.hosted_account_orchestrator import (
    CREATE_ACCOUNT,
    EMAIL_VERIFICATION,
    EXISTING_ACCOUNT,
    LOGIN,
    RESUME_APPLICATION,
    VERIFIED,
    HostedAccountOrchestrator,
)

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

REGISTER_URL = "https://careers.example.com/candidate/register"
LOGIN_URL = "https://careers.example.com/candidate/login"
VERIFY_URL = "https://careers.example.com/candidate/verify/browser-token"
NOW = "2026-09-19T02:00:00+00:00"
EXISTING_CREDENTIAL_REFERENCE = "ats-secret://account-existing-browser/password"


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
            if (sameSession && validCode) {
              history.replaceState({}, "", "/candidate/dashboard");
            }
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
      if (sameSession) {
        history.replaceState({}, "", "/candidate/dashboard");
      }
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



class _LoginBridge:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def mailbox_health(self, _plan: dict[str, object]) -> dict[str, object]:
        return {
            "ready": True,
            "mandatory": True,
            "relay_ready": True,
            "signing_ready": True,
            "encryption_ready": True,
        }

    def account_password(
        self,
        _plan: dict[str, object],
        *,
        account_id: str,
        secret_ref: str,
    ) -> str:
        assert account_id == "account-existing-browser"
        assert secret_ref == EXISTING_CREDENTIAL_REFERENCE
        return "Fixture-Existing-Managed-1!"

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
        assert account_id == "account-existing-browser"
        assert provider == "EXAMPLE"
        assert expected_link_hosts == ["careers.example.com"]
        assert expected_sender_domains == ["mail.example.com"]
        assert ttl_minutes == 30
        return {"request_id": "request-existing-login", "mail_relay_ready": True}

    def cancel_mailbox_verification(
        self,
        _plan: dict[str, object],
        *,
        request_id: str,
        account_id: str,
        reason_code: str,
    ) -> dict[str, str]:
        assert request_id == "request-existing-login"
        assert account_id == "account-existing-browser"
        self.cancelled.append(reason_code)
        return {"request_id": request_id, "state": "CANCELLED"}


def _existing_login_plan(application_id: str) -> dict[str, object]:
    plan = _plan(application_id)
    plan["job"] = {
        "apply_url": LOGIN_URL,
        "job_url": LOGIN_URL,
        "company": "Browser Fixture",
    }
    return plan


def _existing_login_html() -> str:
    return """<!doctype html>
<html>
  <body>
    <h1>Returning candidate login</h1>
    <form id="login">
      <input type="email" autocomplete="username" name="email" />
      <input type="password" autocomplete="current-password" name="password" />
      <button type="submit">Sign in</button>
    </form>
    <script>
      document.querySelector("#login").addEventListener("submit", (event) => {
        event.preventDefault();
        const email = document.querySelector("input[type=email]").value;
        const password = document.querySelector("input[type=password]").value;
        if (
          email === "u_existingbrowser0001@mail.munshi.systems" &&
          password === "Fixture-Existing-Managed-1!"
        ) {
          sessionStorage.setItem("munshi-existing-login", "same-context");
          history.replaceState({}, "", "/candidate/dashboard");
          document.body.innerHTML =
            "<h1>Candidate dashboard</h1><p>Application can resume.</p>";
        }
      });
    </script>
  </body>
</html>"""


def test_existing_account_login_uses_managed_credential_and_persists_same_session(
    tmp_path: Path,
) -> None:
    application_id = "app-browser-existing-login"
    database = _database(tmp_path, application_id)
    plan = _existing_login_plan(application_id)
    bridge = _LoginBridge()

    AccountStore(database).upsert(
        {
            "accountId": "account-existing-browser",
            "employer": "Browser Fixture",
            "portalUrl": LOGIN_URL,
            "email": "u_existingbrowser0001@mail.munshi.systems",
            "exists": True,
            "applicationId": application_id,
            "observedAt": NOW,
        }
    )
    ATSAccountLifecycle(database).provision(
        {
            "accountId": "account-existing-browser",
            "provider": "example",
            "credentialRef": EXISTING_CREDENTIAL_REFERENCE,
            "mailAlias": "u_existingbrowser0001@mail.munshi.systems",
            "observedAt": NOW,
        }
    )

    browser_path = resolve_browser_executable()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=browser_path,
        )
        context = browser.new_context()

        def handler(route: object) -> None:
            request = route.request
            if request.url == LOGIN_URL and request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=_existing_login_html(),
                )
                return
            route.abort()

        context.route("**/*", handler)
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        result = HostedAccountOrchestrator(
            database,
            plan=plan,
            bridge=bridge,
            page=page,
            context=context,
            tenant_id="tenant-browser",
            user_id="user-browser",
            session_secret=b"browser-existing-login-session-fixture",
            verification_timeout_seconds=5,
            poll_interval_seconds=0.05,
        ).run()

        assert result.state == RESUME_APPLICATION
        assert EXISTING_ACCOUNT in result.trace
        assert LOGIN in result.trace
        assert result.trace[-1] == RESUME_APPLICATION
        assert bridge.cancelled == ["VERIFICATION_NOT_REQUIRED"]
        assert (
            page.evaluate("sessionStorage.getItem('munshi-existing-login')")
            == "same-context"
        )

        with database.connect() as connection:
            persisted = connection.execute(
                """
                SELECT account_id,ciphertext,expires_at,invalidated_at
                FROM hosted_account_sessions
                WHERE tenant_id='tenant-browser'
                  AND user_id='user-browser'
                  AND scope_key='careers.example.com'
                """
            ).fetchone()

        assert persisted is not None
        assert persisted["account_id"] == "account-existing-browser"
        assert bytes(persisted["ciphertext"])
        assert persisted["expires_at"]
        assert persisted["invalidated_at"] is None

        context.close()
        browser.close()


class _WorkdayLoginBridge(_LoginBridge):
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
        assert account_id == "account-existing-browser"
        assert provider == "WORKDAY"
        assert expected_link_hosts == ["careers.example.com"]
        assert expected_sender_domains == ["mail.example.com"]
        assert ttl_minutes == 30
        return {"request_id": "request-existing-login", "mail_relay_ready": True}


def _workday_duplicate_auth_forms_html() -> str:
    return """<!doctype html>
<html>
  <body>
    <h1>Create Account</h1>
    <form id="create-form">
      <input type="text" autocomplete="email" data-automation-id="email" />
      <input type="password" autocomplete="new-password" data-automation-id="password" />
      <input type="password" autocomplete="new-password" data-automation-id="verifyPassword" />
      <input type="checkbox" data-automation-id="createAccountCheckbox" />
      <button type="submit" data-automation-id="createAccountSubmitButton">Create Account</button>
    </form>
    <button type="button" data-automation-id="signInLink">Sign In</button>
    <form id="login-form" style="display:none">
      <h2>Sign In</h2>
      <input type="text" autocomplete="email" data-automation-id="email" />
      <input type="password" autocomplete="current-password" data-automation-id="password" />
      <div style="position:relative;width:160px;height:40px">
        <button type="submit" tabindex="-2" aria-hidden="true"
          style="width:160px;height:40px"
          data-automation-id="signInSubmitButton">Sign In</button>
        <div role="button" tabindex="0" aria-label="Sign In"
          style="position:absolute;inset:0"
          data-automation-id="click_filter"></div>
      </div>
    </form>
    <script>
      document.querySelector("[data-automation-id=signInLink]").addEventListener("click", () => {
        document.querySelector("#login-form").style.display = "block";
      });
      document.querySelector("#login-form").addEventListener("submit", (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const email = form.querySelector("[data-automation-id=email]").value;
        const password = form.querySelector("[data-automation-id=password]").value;
        if (
          email === "u_existingbrowser0001@mail.munshi.systems" &&
          password === "Fixture-Existing-Managed-1!"
        ) {
          sessionStorage.setItem("workday-login-form", "scoped");
          history.replaceState({}, "", location.pathname + "/apply/autofillWithResume");
          document.body.innerHTML = "<h1>Candidate dashboard</h1>";
        }
      });
      document.querySelector("#login-form [data-automation-id=click_filter]")
        .addEventListener("click", () => document.querySelector("#login-form").requestSubmit());
    </script>
  </body>
</html>"""


def test_workday_login_scopes_fields_and_submit_to_login_form(tmp_path: Path) -> None:
    application_id = "app-browser-workday-login"
    database = _database(tmp_path, application_id)
    plan = _plan(application_id)
    plan["provider_policy"]["provider"] = "WORKDAY"  # type: ignore[index]
    bridge = _WorkdayLoginBridge()

    AccountStore(database).upsert(
        {
            "accountId": "account-existing-browser",
            "employer": "Browser Fixture",
            "portalUrl": REGISTER_URL,
            "email": "u_existingbrowser0001@mail.munshi.systems",
            "exists": True,
            "applicationId": application_id,
            "observedAt": NOW,
        }
    )
    ATSAccountLifecycle(database).provision(
        {
            "accountId": "account-existing-browser",
            "provider": "workday",
            "credentialRef": EXISTING_CREDENTIAL_REFERENCE,
            "mailAlias": "u_existingbrowser0001@mail.munshi.systems",
            "observedAt": NOW,
        }
    )

    browser_path = resolve_browser_executable()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=browser_path)
        context = browser.new_context()
        context.route(
            "**/*",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body=_workday_duplicate_auth_forms_html(),
            ),
        )
        page = context.new_page()
        page.goto(REGISTER_URL, wait_until="domcontentloaded")

        result = HostedAccountOrchestrator(
            database,
            plan=plan,
            bridge=bridge,
            page=page,
            context=context,
            tenant_id="tenant-browser",
            user_id="user-browser",
            session_secret=b"browser-workday-login-session-fixture",
            verification_timeout_seconds=5,
            poll_interval_seconds=0.05,
        ).run()

        assert result.state == RESUME_APPLICATION
        assert LOGIN in result.trace
        assert page.evaluate("sessionStorage.getItem('workday-login-form')") == "scoped"
        assert bridge.cancelled == ["VERIFICATION_NOT_REQUIRED"]

        context.close()
        browser.close()


def test_text_click_uses_visible_match_when_hidden_duplicate_comes_first(
    tmp_path: Path,
) -> None:
    application_id = "app-browser-visible-text-control"
    database = _database(tmp_path, application_id)
    plan = _plan(application_id)
    bridge = _Bridge("visible-text-control")

    browser_path = resolve_browser_executable()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=browser_path)
        context = browser.new_context()
        page = context.new_page()
        page.set_content(
            """
            <button style="display:none">Forgot your password?</button>
            <button id="visible-recovery">Forgot your password?</button>
            <script>
              document.querySelector('#visible-recovery').addEventListener('click', () => {
                document.body.dataset.recoveryClicked = 'yes';
              });
            </script>
            """
        )
        orchestrator = HostedAccountOrchestrator(
            database,
            plan=plan,
            bridge=bridge,
            page=page,
            context=context,
            tenant_id="tenant-browser",
            user_id="user-browser",
            session_secret=b"browser-visible-control-session-fixture",
        )

        orchestrator._click_text(
            re.compile(r"forgot (?:your )?password", re.I),
            "password recovery",
        )

        assert page.evaluate("document.body.dataset.recoveryClicked") == "yes"
        context.close()
        browser.close()


class _WorkdayRetryBridge(_Bridge):
    def __init__(self) -> None:
        super().__init__("workday-retry")
        self.prepare_calls = 0

    def prepare_managed_account(self, *args: object, **kwargs: object) -> dict[str, str]:
        self.prepare_calls += 1
        raise AssertionError("An incomplete account retry must reuse its managed identity")

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
        assert account_id == "account-browser-workday-retry"
        assert provider == "WORKDAY"
        assert expected_link_hosts == ["careers.example.com"]
        assert expected_sender_domains == ["mail.example.com"]
        assert ttl_minutes == 30
        return {"request_id": "request-workday-retry", "mail_relay_ready": True}


def _workday_retry_html() -> str:
    return """<!doctype html>
<html>
  <body>
    <h1 id="account-heading">Loading</h1>
    <form id="create-account" style="display:none">
      <input type="text" autocomplete="email" data-automation-id="email" />
      <input type="password" autocomplete="new-password" data-automation-id="password" />
      <input type="password" autocomplete="new-password" data-automation-id="verifyPassword" />
      <input type="checkbox" data-automation-id="createAccountCheckbox" />
      <label>I agree</label>
      <input type="text" name="website" data-automation-id="beecatcher" />
      <div style="position:relative;width:160px;height:40px">
        <button type="submit" tabindex="-2" aria-hidden="true"
          style="width:160px;height:40px"
          data-automation-id="createAccountSubmitButton">Create Account</button>
        <div role="button" tabindex="0" aria-label="Create Account"
          style="position:absolute;inset:0"
          data-automation-id="click_filter"></div>
      </div>
    </form>
    <script>
      sessionStorage.setItem("munshi-account-flow", "same-context");
      setTimeout(() => {
        document.querySelector("#account-heading").textContent = "Create Account";
        document.querySelector("#create-account").style.display = "block";
      }, 350);
      document.querySelector("#create-account").addEventListener("submit", (event) => {
        event.preventDefault();
        const consent = document.querySelector("[data-automation-id=createAccountCheckbox]");
        const trap = document.querySelector("[data-automation-id=beecatcher]");
        sessionStorage.setItem("workday-consent", String(consent.checked));
        sessionStorage.setItem("workday-beecatcher", trap.value);
        if (consent.checked && trap.value === "") {
          document.body.innerHTML = "<h1>Check your email to verify your account</h1>";
        }
      });
      document.querySelector("#create-account [data-automation-id=click_filter]")
        .addEventListener("click", () => document.querySelector("#create-account").requestSubmit());
    </script>
  </body>
</html>"""


def test_failed_safe_workday_creation_reuses_account_and_handles_current_controls(
    tmp_path: Path,
) -> None:
    application_id = "app-browser-workday-retry"
    database = _database(tmp_path, application_id)
    plan = _plan(application_id)
    plan["provider_policy"]["provider"] = "WORKDAY"  # type: ignore[index]
    bridge = _WorkdayRetryBridge()
    account_id = "account-browser-workday-retry"
    email = "u_workdayretry0001@mail.munshi.systems"
    secret_ref = f"ats-secret://{account_id}/password"

    AccountStore(database).upsert(
        {
            "accountId": account_id,
            "employer": "Browser Fixture",
            "portalUrl": REGISTER_URL,
            "email": email,
            "exists": False,
            "applicationId": application_id,
            "observedAt": NOW,
        }
    )
    lifecycle = ATSAccountLifecycle(database)
    lifecycle.provision(
        {
            "accountId": account_id,
            "provider": "workday",
            "credentialRef": secret_ref,
            "mailAlias": email,
            "observedAt": NOW,
        }
    )
    lifecycle.begin_creation(account_id, NOW)
    lifecycle.mark_issue(
        account_id=account_id,
        application_id=application_id,
        continuation_id=None,
        issue_code="ACCOUNT_CREATION_FAILED",
        observed_at=NOW,
    )

    browser_path = resolve_browser_executable()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=browser_path)
        context = browser.new_context()

        def handler(route: object) -> None:
            request = route.request
            if request.url == REGISTER_URL and request.method == "GET":
                route.fulfill(status=200, content_type="text/html", body=_workday_retry_html())
                return
            if request.url == VERIFY_URL and request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="""<!doctype html><body>
                    <h1>Email verified. Your account is now active.</h1>
                    <script>
                      history.replaceState(
                        {}, '', '/candidate/register/apply/autofillWithResume'
                      );
                    </script>
                    </body>""",
                )
                return
            route.abort()

        context.route("**/*", handler)
        page = context.new_page()
        page.goto(REGISTER_URL, wait_until="domcontentloaded")

        result = HostedAccountOrchestrator(
            database,
            plan=plan,
            bridge=bridge,
            page=page,
            context=context,
            tenant_id="tenant-browser",
            user_id="user-browser",
            session_secret=b"browser-workday-retry-session-fixture",
            verification_timeout_seconds=5,
            poll_interval_seconds=0.05,
        ).run()

        assert result.account_id == account_id
        assert EXISTING_ACCOUNT in result.trace
        assert CREATE_ACCOUNT in result.trace
        assert LOGIN not in result.trace
        assert result.state == RESUME_APPLICATION
        assert bridge.prepare_calls == 0
        assert page.evaluate("sessionStorage.getItem('workday-consent')") == "true"
        assert page.evaluate("sessionStorage.getItem('workday-beecatcher')") == ""
        assert AccountStore(database).lookup({"portalUrl": REGISTER_URL})[0]["exists"] is True
        assert lifecycle.snapshot(account_id)["state"] == "AUTHENTICATED"

        context.close()
        browser.close()
