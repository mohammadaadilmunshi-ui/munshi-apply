from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.hosted_trust_worker import (
    TrustAwareAdapterFactory,
    UserAuthRequired,
)
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

JOB_URL = "https://jobs.example.test/apply/42"


class _TrustStore:
    def __init__(self) -> None:
        self.active = None
        self.cleared: list[dict[str, object]] = []

    def observe(self, **kwargs):
        self.active = {
            "trust_checkpoint_id": "trust-browser-1",
            "checkpoint_kind": kwargs["checkpoint_kind"],
            "status": "WAITING_FOR_USER_AUTH",
        }
        return dict(self.active)

    def active_for_job(self, **_kwargs):
        return None if self.active is None else dict(self.active)

    def clear_after_live_browser_revalidation(self, **kwargs):
        self.cleared.append(dict(kwargs))
        cleared = dict(self.active or {})
        cleared["status"] = "CLEARED"
        self.active = None
        return cleared


class _Queue:
    def __init__(self) -> None:
        self.requeued: list[dict[str, object]] = []

    def requeue_session(self, **kwargs):
        self.requeued.append(dict(kwargs))
        return {"job_id": "prepare-browser-1", "state": "QUEUED"}


def _plan() -> dict[str, object]:
    return {
        "job": {
            "id": "42",
            "company": "Checkpoint Fixture",
            "title": "People Analyst",
            "job_url": JOB_URL,
            "apply_url": JOB_URL,
        },
        "provider_policy": {"provider": "GENERIC"},
        "answers": [],
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
        },
    }


def _job() -> dict[str, str]:
    return {
        "job_id": "prepare-browser-1",
        "tenant_id": "tenant-browser",
        "user_id": "user-browser",
        "session_id": "session-browser-1",
    }


def _runtime() -> Path:
    root = Path(__file__).resolve().parents[4]
    runtime = root / "apps/native-host/browser-dist/plan-runtime.js"
    assert runtime.is_file(), "run npm run build before the real-browser lane"
    return runtime


@pytest.mark.parametrize(
    ("expected_kind", "challenge_html"),
    [
        (
            "CAPTCHA",
            "<p>Please complete the CAPTCHA verification to continue.</p>",
        ),
        (
            "MFA",
            "<p>Two-factor authentication is required. Approve the SMS challenge.</p>",
        ),
        (
            "OTP",
            "<p>Enter the SMS verification code we sent to your mobile phone.</p>",
        ),
        (
            "AUTHENTICATION",
            "<h1>Sign in with your passkey</h1><button>Use security key</button>",
        ),
    ],
)
def test_security_checkpoint_resumes_only_in_same_revalidated_chromium_context(
    expected_kind: str,
    challenge_html: str,
) -> None:
    browser_path = resolve_browser_executable()
    trust = _TrustStore()
    queue = _Queue()
    plan = _plan()
    job = _job()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=browser_path,
        )
        context = browser.new_context()

        def handler(route):
            if route.request.url == JOB_URL:
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=f"<!doctype html><html><body>{challenge_html}</body></html>",
                )
                return
            route.abort()

        context.route("**/*", handler)
        page = context.new_page()
        page.goto(JOB_URL, wait_until="domcontentloaded")

        delegate = PlanBrowserAdapter(
            page,
            artifact_reader=lambda _plan: b"",
            current_plan=lambda current: current == plan,
            runtime_path=_runtime(),
        )
        factory = TrustAwareAdapterFactory(lambda _job: delegate, trust)
        wrapped = factory(job)

        with pytest.raises(UserAuthRequired) as raised:
            wrapped.inspect_job(plan=plan)
        assert raised.value.checkpoint["checkpoint_kind"] == expected_kind

        wrapped.park_for_user_auth(raised.value.checkpoint)
        wrapped.close()

        # This mutation stands in for the legitimate user completing the protected
        # challenge. MUNSHI never solves CAPTCHA, SMS MFA, or passkeys itself.
        page.evaluate(
            """() => {
              document.body.innerHTML =
                '<h1>People Analyst</h1><p>Application ready.</p>';
            }"""
        )

        assert factory.resume_ready_checkpoints(queue) == 1
        assert trust.cleared
        assert queue.requeued == [
            {
                "session_id": "session-browser-1",
                "tenant_id": "tenant-browser",
                "user_id": "user-browser",
            }
        ]

        resumed = factory(job)
        assert resumed is wrapped
        observation = resumed.inspect_job(plan=plan)
        assert observation["security_checkpoint"] is None
        assert observation["job_id"] == "42"
        assert page.url == JOB_URL

        context.close()
        browser.close()
