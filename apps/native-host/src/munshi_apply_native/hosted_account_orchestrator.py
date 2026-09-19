"""Executable hosted ATS account orchestrator.

State machine:
ACCOUNT_REQUIRED -> EXISTING_ACCOUNT -> LOGIN / CREATE_ACCOUNT ->
PASSWORD_CREATION -> EMAIL_VERIFICATION -> VERIFIED -> RESUME_APPLICATION.

It runs in the same Playwright page/context used for the application. Hunter is
the only mailbox/credential authority; Apply persists only opaque references,
digests, lifecycle metadata, and encrypted Chromium storage state.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .account_store import AccountStore, portal_identity
from .artifact_fetch_v2 import HunterExecutionBridgeClient
from .ats_account_lifecycle import ATSAccountLifecycle, ATSAccountLifecycleError
from .database import Database
from .hosted_account_session import HostedAccountSessionStore

ACCOUNT_REQUIRED = "ACCOUNT_REQUIRED"
EXISTING_ACCOUNT = "EXISTING_ACCOUNT"
LOGIN = "LOGIN"
CREATE_ACCOUNT = "CREATE_ACCOUNT"
PASSWORD_CREATION = "PASSWORD_CREATION"
EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
VERIFIED = "VERIFIED"
RESUME_APPLICATION = "RESUME_APPLICATION"
ISSUE = "ISSUE"
NOT_REQUIRED = "NOT_REQUIRED"

_TERMINAL_ISSUE_CODES = {
    "MAILBOX_RUNTIME_UNAVAILABLE",
    "MAILBOX_PROVIDER_POLICY_UNAVAILABLE",
    "MAILBOX_VERIFICATION_TIMEOUT",
    "MAILBOX_VERIFICATION_FAILED",
    "ACCOUNT_CREDENTIAL_REFERENCE_MISSING",
    "ACCOUNT_LOGIN_FAILED",
    "ACCOUNT_CREATION_FAILED",
    "ACCOUNT_RECOVERY_FAILED",
    "DUPLICATE_ACCOUNT_DETECTED",
    "ACCOUNT_USERNAME_POLICY_UNSUPPORTED",
    "ACCOUNT_SESSION_PERSISTENCE_FAILED",
}

_ACCOUNT_ROUTE = re.compile(
    r"\b(login|log-in|signin|sign-in|register|signup|sign-up|create-account|candidate-account|forgot|reset|verify)\b",
    re.IGNORECASE,
)
_ACCOUNT_TEXT = re.compile(
    r"\b(sign in|log in|login|create (?:an? )?account|register|sign up|forgot (?:your )?password|"
    r"verify (?:your )?(?:email|account)|verification code|enter the code we sent)\b",
    re.IGNORECASE,
)
_VERIFY_TEXT = re.compile(
    r"\b(verify (?:your )?(?:email|account)|verification code|enter the code|code we sent|check your email)\b",
    re.IGNORECASE,
)
_CREATE_TEXT = re.compile(
    r"\b(create (?:an? )?account|register|sign up|new candidate)\b",
    re.IGNORECASE,
)
_LOGIN_TEXT = re.compile(r"\b(sign in|log in|login|returning candidate)\b", re.IGNORECASE)
_RECOVERY_TEXT = re.compile(
    r"\b(forgot (?:your )?(?:password|username)|reset (?:your )?password|account recovery)\b",
    re.IGNORECASE,
)
_VERIFICATION_SUCCESS_TEXT = re.compile(
    r"\b(email (?:has been )?verified|email verified|account verified|verification complete|"
    r"successfully verified|account activated|email confirmed|verification successful)\b",
    re.IGNORECASE,
)
_VERIFICATION_FAILURE_TEXT = re.compile(
    r"\b(invalid (?:verification )?(?:link|code)|expired (?:verification )?(?:link|code)|"
    r"verification failed|unable to verify|link has expired|code is incorrect|incorrect code)\b",
    re.IGNORECASE,
)


class HostedAccountIssue(RuntimeError):
    def __init__(self, issue_code: str, message: str) -> None:
        self.issue_code = str(issue_code or "ACCOUNT_ORCHESTRATION_ISSUE").upper()
        super().__init__(message)


@dataclass(frozen=True)
class HostedAccountResult:
    state: str
    account_id: str | None
    continuation_id: str | None
    trace: tuple[str, ...]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class HostedAccountOrchestrator:
    def __init__(
        self,
        database: Database,
        *,
        plan: dict[str, Any],
        bridge: HunterExecutionBridgeClient,
        page: Any,
        context: Any,
        verification_timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 2.0,
        sleeper: Any = time.sleep,
    ) -> None:
        self.database = database
        self.plan = plan
        self.bridge = bridge
        self.page = page
        self.context = context
        self.verification_timeout_seconds = max(5.0, float(verification_timeout_seconds))
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds))
        self.sleeper = sleeper
        self.store = AccountStore(database)
        self.lifecycle = ATSAccountLifecycle(database)
        self.session_store = HostedAccountSessionStore(
            database, bridge_secret=self.bridge.secret
        )
        self.trace: list[str] = []
        self.account_id: str | None = None
        self.continuation_id: str | None = None
        self.original_url = str(plan["job"].get("apply_url") or plan["job"].get("job_url") or "")
        self.provider = str(plan["provider_policy"]["provider"]).strip().upper()
        self.application_id = str(plan["application_id"])
        self.scope_key = portal_identity(self.original_url)[1]

    def _event(self, state: str, issue_code: str | None = None) -> None:
        self.trace.append(state if issue_code is None else f"{state}:{issue_code}")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO hosted_account_orchestration_events(
                  event_id,tenant_id,user_id,application_id,account_id,
                  continuation_id,state,issue_code,occurred_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"acctevt_{uuid4().hex}",
                    self.bridge.tenant_id,
                    self.bridge.user_id,
                    self.application_id,
                    self.account_id,
                    self.continuation_id,
                    state,
                    issue_code,
                    _now(),
                ),
            )

    def _text(self) -> str:
        parts = [str(getattr(self.page, "url", "") or "")]
        try:
            parts.append(str(self.page.title() or ""))
        except Exception:
            pass
        try:
            parts.append(str(self.page.locator("body").inner_text(timeout=1500) or "")[:20000])
        except Exception:
            pass
        return " ".join(parts)

    def _visible(self, selectors: list[str]) -> Any | None:
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() and locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    def _account_required(self) -> bool:
        text = self._text()
        try:
            path = urlsplit(str(self.page.url)).path
        except Exception:
            path = ""
        if _ACCOUNT_ROUTE.search(path) or _ACCOUNT_TEXT.search(text):
            return True
        return self._visible(
            [
                "input[type='password']",
                "input[autocomplete='current-password']",
                "input[autocomplete='new-password']",
                "input[autocomplete='one-time-code']",
            ]
        ) is not None

    def _is_verification(self) -> bool:
        if self._visible(
            [
                "input[autocomplete='one-time-code']",
                "input[name*='verification' i]",
                "input[name*='otp' i]",
                "input[id*='verification' i]",
                "input[id*='otp' i]",
            ]
        ) is not None:
            return True
        return bool(_VERIFY_TEXT.search(self._text()))

    def _is_login(self) -> bool:
        return self._visible(
            ["input[type='password']", "input[autocomplete='current-password']"]
        ) is not None and bool(_LOGIN_TEXT.search(self._text()))

    def _is_create(self) -> bool:
        return self._visible(
            ["input[type='password']", "input[autocomplete='new-password']"]
        ) is not None and bool(_CREATE_TEXT.search(self._text()))

    def _fill_first(self, selectors: list[str], value: str, label: str) -> None:
        locator = self._visible(selectors)
        if locator is None:
            raise HostedAccountIssue("ACCOUNT_FORM_UNSUPPORTED", f"{label} field was not found")
        locator.fill(value)

    def _click_text(self, pattern: re.Pattern[str], label: str) -> None:
        for role in ("button", "link"):
            try:
                locator = self.page.get_by_role(role, name=pattern).first
                if locator.count() and locator.is_visible():
                    locator.click()
                    return
            except Exception:
                continue
        try:
            locator = self.page.get_by_text(pattern).first
            if locator.count() and locator.is_visible():
                locator.click()
                return
        except Exception:
            pass
        raise HostedAccountIssue("ACCOUNT_FORM_UNSUPPORTED", f"{label} control was not found")

    def _wait_page(self, milliseconds: int = 800) -> None:
        try:
            self.page.wait_for_timeout(milliseconds)
        except Exception:
            self.sleeper(milliseconds / 1000.0)

    def _login_identifier(self, email: str) -> str:
        policy = dict(self.plan.get("provider_policy") or {})
        account_policy = policy.get("account_identity")
        if not isinstance(account_policy, dict):
            account_policy = {}
        mode = str(
            account_policy.get("username_policy")
            or policy.get("username_policy")
            or "EMAIL"
        ).strip().upper()
        if mode in {"EMAIL", "APPLICATION_EMAIL", "MAIL_ALIAS"}:
            return email
        if mode == "EMAIL_LOCAL_PART":
            local, separator, _domain = email.partition("@")
            if separator and local:
                return local
        self._issue(
            "ACCOUNT_USERNAME_POLICY_UNSUPPORTED",
            f"Unsupported ATS username policy: {mode}",
        )
        raise AssertionError("unreachable")

    def _mailbox_policy(self) -> tuple[list[str], list[str]]:
        policy = dict(self.plan.get("provider_policy") or {})
        mailbox = policy.get("mailbox_verification")
        if not isinstance(mailbox, dict):
            mailbox = {}
        senders = mailbox.get("sender_domains") or policy.get("verification_sender_domains") or []
        hosts = (
            mailbox.get("link_hosts")
            or policy.get("verification_link_hosts")
            or policy.get("allowed_hosts")
            or []
        )
        senders = [str(v).strip().casefold().rstrip(".") for v in senders if str(v).strip()]
        hosts = [str(v).strip().casefold().rstrip(".") for v in hosts if str(v).strip()]
        if not senders or not hosts:
            raise HostedAccountIssue(
                "MAILBOX_PROVIDER_POLICY_UNAVAILABLE",
                "Provider mailbox sender/link policy is not configured",
            )
        return list(dict.fromkeys(hosts)), list(dict.fromkeys(senders))

    def _bind_continuation(self, account_id: str) -> str:
        continuation_id = f"acctcont_{uuid4().hex}"
        self.lifecycle.bind_continuation(
            {
                "continuationId": continuation_id,
                "accountId": account_id,
                "applicationId": self.application_id,
                "executionSessionId": f"hosted-{self.plan['plan_id']}",
                "provider": self.provider.lower(),
                "targetFingerprint": _fingerprint(self.original_url),
                "observedAt": _now(),
            }
        )
        self.continuation_id = continuation_id
        return continuation_id

    def _issue(self, code: str, message: str) -> None:
        normalized = str(code).upper()
        self._event(ISSUE, normalized)
        if self.account_id is not None:
            try:
                self.session_store.invalidate(
                    tenant_id=self.bridge.tenant_id,
                    user_id=self.bridge.user_id,
                    scope_key=self.scope_key,
                    reason=normalized,
                )
            except Exception:
                pass
            try:
                self.lifecycle.mark_issue(
                    account_id=self.account_id,
                    application_id=self.application_id,
                    continuation_id=self.continuation_id,
                    issue_code=normalized,
                    observed_at=_now(),
                )
            except Exception:
                pass
        raise HostedAccountIssue(normalized, message)

    def _mailbox_ready(self) -> None:
        try:
            health = self.bridge.mailbox_health(self.plan)
        except Exception as error:
            self._issue("MAILBOX_RUNTIME_UNAVAILABLE", "Mandatory mailbox runtime is unavailable")
        if health.get("ready") is not True or health.get("mandatory") is not True:
            self._issue("MAILBOX_RUNTIME_UNAVAILABLE", "Mandatory mailbox runtime is unavailable")

    def _arm_mailbox(self, account_id: str) -> dict[str, Any]:
        self._mailbox_ready()
        try:
            hosts, senders = self._mailbox_policy()
            return self.bridge.begin_mailbox_verification(
                self.plan,
                account_id=account_id,
                provider=self.provider,
                expected_link_hosts=hosts,
                expected_sender_domains=senders,
                ttl_minutes=30,
            )
        except HostedAccountIssue:
            raise
        except Exception:
            self._issue(
                "MAILBOX_RUNTIME_UNAVAILABLE",
                "Mandatory mailbox verification could not be armed",
            )
        raise AssertionError("unreachable")

    def _cancel_mailbox_request(
        self,
        *,
        mailbox_request: dict[str, Any] | None,
        account_id: str,
        reason_code: str = "VERIFICATION_NOT_REQUIRED",
    ) -> None:
        if not mailbox_request or not mailbox_request.get("request_id"):
            return
        try:
            self.bridge.cancel_mailbox_verification(
                self.plan,
                request_id=str(mailbox_request["request_id"]),
                account_id=account_id,
                reason_code=reason_code,
            )
        except Exception:
            # Cancellation is cleanup only. A request still has its Hunter TTL,
            # and failure to cancel must not turn a completed login into ISSUE.
            return

    def _claim_mail(
        self, *, request_id: str, account_id: str, expected_kind: str
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.verification_timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self.bridge.claim_mailbox_verification(
                    self.plan,
                    request_id=request_id,
                    account_id=account_id,
                    expected_kind=expected_kind,
                )
            except Exception as error:
                last_error = error
                self.sleeper(self.poll_interval_seconds)
        try:
            health = self.bridge.mailbox_health(self.plan)
        except Exception:
            health = {"ready": False}
        if health.get("ready") is not True:
            self._issue("MAILBOX_RUNTIME_UNAVAILABLE", "Mandatory mailbox runtime became unavailable")
        self._issue(
            "MAILBOX_VERIFICATION_TIMEOUT",
            "Timed out waiting for correlated verification email",
        )
        if last_error:
            raise last_error
        raise AssertionError("unreachable")

    def _verification_kind(self) -> str:
        if self._visible(
            [
                "input[autocomplete='one-time-code']",
                "input[name*='verification' i]",
                "input[name*='otp' i]",
                "input[id*='otp' i]",
            ]
        ) is not None:
            return "EMAIL_VERIFICATION_CODE"
        return "EMAIL_VERIFICATION_LINK"

    def _verification_confirmed(self, artifact_kind: str) -> bool:
        text = self._text()
        if _VERIFICATION_FAILURE_TEXT.search(text):
            return False
        if artifact_kind == "PASSWORD_RESET_LINK":
            return self._visible(
                ["input[autocomplete='new-password']", "input[type='password']"]
            ) is not None
        if _VERIFICATION_SUCCESS_TEXT.search(text):
            return True
        if artifact_kind == "EMAIL_VERIFICATION_CODE":
            return not self._is_verification()
        if artifact_kind == "MAGIC_LOGIN_LINK":
            return not self._is_login() and not self._is_verification()
        # For ordinary email links, require an explicit success marker instead
        # of treating HTTP navigation itself as proof.
        return False

    def _apply_verification(self, artifact_kind: str, artifact: str) -> bool:
        if artifact_kind == "EMAIL_VERIFICATION_CODE":
            self._fill_first(
                [
                    "input[autocomplete='one-time-code']",
                    "input[name*='verification' i]",
                    "input[name*='code' i]",
                    "input[name*='otp' i]",
                    "input[id*='verification' i]",
                    "input[id*='otp' i]",
                ],
                artifact,
                "verification code",
            )
            self._click_text(
                re.compile(r"^(verify|confirm|continue|submit)(?:\s+(?:email|code|account))?$", re.I),
                "verification",
            )
            self._wait_page(1000)
            return self._verification_confirmed(artifact_kind)

        if artifact_kind in {
            "EMAIL_VERIFICATION_LINK",
            "PASSWORD_RESET_LINK",
            "MAGIC_LOGIN_LINK",
        }:
            self.page.goto(artifact, wait_until="domcontentloaded")
            self._wait_page(800)
            return self._verification_confirmed(artifact_kind)
        return False

    def _verify_with_mailbox(
        self,
        *,
        account_id: str,
        mailbox_request: dict[str, Any],
        artifact_kind: str | None = None,
    ) -> None:
        self._event(EMAIL_VERIFICATION)
        kind = artifact_kind or self._verification_kind()
        lifecycle_kind = {
            "EMAIL_VERIFICATION_CODE": "EMAIL_CODE",
            "EMAIL_VERIFICATION_LINK": "EMAIL_LINK",
            "PASSWORD_RESET_LINK": "PASSWORD_RESET_LINK",
            "MAGIC_LOGIN_LINK": "MAGIC_LOGIN_LINK",
        }[kind]
        challenge_id = f"acctchallenge_{uuid4().hex}"
        self.lifecycle.start_verification(
            {
                "challengeId": challenge_id,
                "accountId": account_id,
                "applicationId": self.application_id,
                "continuationId": self.continuation_id,
                "kind": lifecycle_kind,
                "observedAt": _now(),
            }
        )
        claimed = self._claim_mail(
            request_id=str(mailbox_request["request_id"]),
            account_id=account_id,
            expected_kind=kind,
        )
        self.lifecycle.mark_verification_ready(
            {
                "challengeId": challenge_id,
                "mailEventId": str(claimed["inbound_id"]),
                "artifactDigest": str(claimed["artifact_digest"]),
                "observedAt": _now(),
            }
        )
        claimed_local = self.lifecycle.claim_verification(challenge_id, _now())
        if claimed_local.get("claimedNow") is not True:
            self._issue("MAILBOX_VERIFICATION_FAILED", "Verification challenge could not be claimed")
        try:
            verified = self._apply_verification(
                str(claimed["artifact_kind"]), str(claimed["artifact"])
            )
        except Exception:
            self._issue("MAILBOX_VERIFICATION_FAILED", "Verification artifact execution failed")
        if verified is not True:
            self._issue("MAILBOX_VERIFICATION_FAILED", "ATS did not confirm email verification")
        try:
            self.bridge.consume_mailbox_verification(
                self.plan,
                artifact_id=str(claimed["artifact_id"]),
                request_id=str(claimed["request_id"]),
                account_id=account_id,
                lease_token=str(claimed["lease_token"]),
            )
        except Exception:
            self._issue(
                "MAILBOX_VERIFICATION_FAILED",
                "Verification succeeded but one-time artifact consumption was ambiguous",
            )
        self.lifecycle.mark_verified(account_id, self.application_id, _now())
        self.lifecycle.consume_verification(challenge_id, _now())
        self.lifecycle.mark_continuation_ready(str(self.continuation_id), _now())
        self._event(VERIFIED)

    def _password(self, account_id: str, secret_ref: str) -> str:
        self._event(PASSWORD_CREATION)
        try:
            return self.bridge.account_password(
                self.plan, account_id=account_id, secret_ref=secret_ref
            )
        except Exception:
            self._issue(
                "ACCOUNT_CREDENTIAL_REFERENCE_MISSING",
                "Managed ATS credential could not be resolved",
            )
        raise AssertionError("unreachable")

    def _login(self, *, email: str, password: str) -> None:
        self._event(LOGIN)
        login_id = self._login_identifier(email)
        self._fill_first(
            [
                "input[type='email']",
                "input[autocomplete='username']",
                "input[name*='email' i]",
                "input[id*='email' i]",
                "input[name*='user' i]",
            ],
            login_id,
            "account email or username",
        )
        self._fill_first(
            ["input[autocomplete='current-password']", "input[type='password']"],
            password,
            "account password",
        )
        self._click_text(re.compile(r"^(sign in|log in|login|continue)$", re.I), "login")
        self._wait_page(1000)

    def _create(self, *, email: str, password: str) -> None:
        self._event(CREATE_ACCOUNT)
        login_id = self._login_identifier(email)
        self._fill_first(
            [
                "input[type='email']",
                "input[autocomplete='username']",
                "input[name*='email' i]",
                "input[id*='email' i]",
            ],
            login_id,
            "account email or username",
        )
        passwords = [
            "input[autocomplete='new-password']",
            "input[type='password']",
        ]
        locator = self.page.locator(", ".join(passwords))
        count = locator.count()
        if count < 1:
            raise HostedAccountIssue("ACCOUNT_FORM_UNSUPPORTED", "Account password field was not found")
        locator.nth(0).fill(password)
        if count > 1:
            locator.nth(1).fill(password)
        self._click_text(
            re.compile(r"^(create (?:my )?account|register|sign up|continue)$", re.I),
            "create account",
        )
        self._wait_page(1000)

    def _recovery(
        self,
        *,
        account_id: str,
        email: str,
        password: str,
    ) -> None:
        self._event(LOGIN)
        try:
            self._click_text(_RECOVERY_TEXT, "password recovery")
            self._fill_first(
                [
                    "input[type='email']",
                    "input[autocomplete='username']",
                    "input[name*='email' i]",
                ],
                self._login_identifier(email),
                "recovery email or username",
            )
            mailbox_request = self._arm_mailbox(account_id)
            self._click_text(
                re.compile(r"^(send|continue|reset password|email me|submit)$", re.I),
                "send reset email",
            )
            self._verify_with_mailbox(
                account_id=account_id,
                mailbox_request=mailbox_request,
                artifact_kind="PASSWORD_RESET_LINK",
            )
            self._fill_first(
                ["input[autocomplete='new-password']", "input[type='password']"],
                password,
                "new password",
            )
            password_inputs = self.page.locator(
                "input[autocomplete='new-password'], input[type='password']"
            )
            if password_inputs.count() > 1:
                password_inputs.nth(1).fill(password)
            self._click_text(
                re.compile(r"^(save|reset password|set password|continue|submit)$", re.I),
                "save new password",
            )
            self._wait_page(800)
        except HostedAccountIssue:
            raise
        except Exception:
            self._issue("ACCOUNT_RECOVERY_FAILED", "Account recovery failed")

    def _persist_session(self, account_id: str) -> None:
        try:
            state = self.context.storage_state()
            if isinstance(state, dict):
                self.session_store.save(
                    tenant_id=self.bridge.tenant_id,
                    user_id=self.bridge.user_id,
                    scope_key=self.scope_key,
                    account_id=account_id,
                    storage_state=state,
                )
        except Exception:
            self._issue("ACCOUNT_SESSION_PERSISTENCE_FAILED", "Authenticated browser session could not be persisted")

    def _resume(self, account_id: str) -> HostedAccountResult:
        self._event(RESUME_APPLICATION)
        if str(self.page.url) != self.original_url:
            self.page.goto(self.original_url, wait_until="domcontentloaded")
            self._wait_page(500)
        try:
            self.lifecycle.mark_authenticated(account_id, self.application_id, _now())
        except ATSAccountLifecycleError:
            # VERIFIED is sufficient when the portal does not expose a separate
            # authenticated landing transition.
            pass
        if self.continuation_id:
            try:
                snapshot = self.lifecycle.snapshot(account_id)
                matching = [
                    x for x in snapshot.get("continuations", [])
                    if str(x.get("continuation_id")) == self.continuation_id
                ]
                if matching and str(matching[0].get("state")) == "PENDING":
                    self.lifecycle.mark_continuation_ready(self.continuation_id, _now())
                self.lifecycle.consume_continuation(self.continuation_id, _now())
            except Exception:
                pass
        self._persist_session(account_id)
        return HostedAccountResult(
            state=RESUME_APPLICATION,
            account_id=account_id,
            continuation_id=self.continuation_id,
            trace=tuple(self.trace),
        )

    def run(self) -> HostedAccountResult:
        if not self._account_required():
            self._event(NOT_REQUIRED)
            return HostedAccountResult(
                state=NOT_REQUIRED,
                account_id=None,
                continuation_id=None,
                trace=tuple(self.trace),
            )

        self._event(ACCOUNT_REQUIRED)
        records = self.store.lookup({"portalUrl": self.original_url})
        if len(records) > 1:
            self._event(ISSUE, "DUPLICATE_ACCOUNT_DETECTED")
            raise HostedAccountIssue(
                "DUPLICATE_ACCOUNT_DETECTED",
                "Multiple ATS accounts exist for the exact portal scope",
            )

        if records:
            self._event(EXISTING_ACCOUNT)
            record = records[0]
            self.account_id = str(record["accountId"])
            try:
                snapshot = self.lifecycle.snapshot(self.account_id)
            except Exception:
                self._event(ISSUE, "ACCOUNT_CREDENTIAL_REFERENCE_MISSING")
                raise HostedAccountIssue(
                    "ACCOUNT_CREDENTIAL_REFERENCE_MISSING",
                    "Existing ATS account lacks managed lifecycle/credential binding",
                )
            secret_ref = str(snapshot.get("credential_ref") or "")
            if not secret_ref:
                self._issue(
                    "ACCOUNT_CREDENTIAL_REFERENCE_MISSING",
                    "Existing ATS account has no opaque credential reference",
                )
            self._bind_continuation(self.account_id)
            mailbox_request = self._arm_mailbox(self.account_id)
            password = self._password(self.account_id, secret_ref)
            try:
                if self._is_create():
                    self._click_text(re.compile(r"^(sign in|log in|login)$", re.I), "existing account")
                    self._wait_page(500)
                self._login(email=str(record["email"]), password=password)
            finally:
                password = ""
            if self._is_verification():
                self._verify_with_mailbox(
                    account_id=self.account_id,
                    mailbox_request=mailbox_request,
                )
            elif self._is_login():
                self._cancel_mailbox_request(
                    mailbox_request=mailbox_request,
                    account_id=self.account_id,
                    reason_code="LOGIN_RECOVERY_REQUIRED",
                )
                password = self._password(self.account_id, secret_ref)
                try:
                    self._recovery(
                        account_id=self.account_id,
                        email=str(record["email"]),
                        password=password,
                    )
                finally:
                    password = ""
                if self._is_login():
                    self._issue("ACCOUNT_LOGIN_FAILED", "ATS login remained unresolved")
            else:
                self._cancel_mailbox_request(
                    mailbox_request=mailbox_request,
                    account_id=self.account_id,
                )
            return self._resume(self.account_id)

        # No account exists for this exact provider/domain scope.
        if self._is_login() and not self._is_create():
            try:
                self._click_text(_CREATE_TEXT, "create account")
                self._wait_page(500)
            except HostedAccountIssue:
                self._event(ISSUE, "ACCOUNT_CREATION_FAILED")
                raise HostedAccountIssue(
                    "ACCOUNT_CREATION_FAILED",
                    "No existing account exists and the ATS exposes no supported create-account path",
                )

        self._mailbox_ready()
        try:
            prepared = self.bridge.prepare_managed_account(
                self.plan,
                provider=self.provider,
                account_scope=self.scope_key,
                label=f"{self.provider} {self.scope_key}",
            )
        except Exception:
            self._event(ISSUE, "ACCOUNT_CREATION_FAILED")
            raise HostedAccountIssue(
                "ACCOUNT_CREATION_FAILED",
                "Hunter could not prepare managed ATS identity/credential references",
            )
        self.account_id = str(prepared["account_id"])
        email = str(prepared["application_email"])
        secret_ref = str(prepared["secret_ref"])
        self.store.upsert(
            {
                "accountId": self.account_id,
                "portalUrl": self.original_url,
                "email": email,
                "employer": str(self.plan["job"].get("company") or "") or None,
                "exists": False,
                "applicationId": self.application_id,
                "observedAt": _now(),
            }
        )
        self.lifecycle.provision(
            {
                "accountId": self.account_id,
                "provider": self.provider.lower(),
                "credentialRef": secret_ref,
                "mailAlias": email,
                "observedAt": _now(),
            }
        )
        self._bind_continuation(self.account_id)
        self.lifecycle.begin_creation(self.account_id, _now())
        mailbox_request = self._arm_mailbox(self.account_id)
        password = self._password(self.account_id, secret_ref)
        try:
            self._create(email=email, password=password)
        except Exception:
            self._issue("ACCOUNT_CREATION_FAILED", "ATS account creation failed")
        finally:
            password = ""

        verification_required = self._is_verification()
        self.lifecycle.mark_created(
            self.account_id,
            self.application_id,
            _now(),
            verification_required=verification_required,
        )
        if verification_required:
            self._verify_with_mailbox(
                account_id=self.account_id,
                mailbox_request=mailbox_request,
            )
        else:
            self._cancel_mailbox_request(
                mailbox_request=mailbox_request,
                account_id=self.account_id,
            )
        return self._resume(self.account_id)
