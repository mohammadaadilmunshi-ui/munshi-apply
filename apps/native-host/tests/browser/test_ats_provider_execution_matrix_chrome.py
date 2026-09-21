from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

from munshi_apply_native.browser_runtime import resolve_browser_executable  # noqa: E402
from munshi_apply_native.plan_browser_adapter import (  # noqa: E402
    KNOWN_PROVIDER_RECIPES,
    PlanBrowserAdapter,
    provider_for_url,
)

playwright = pytest.importorskip("playwright.sync_api")

SCREENSHOT_PROVIDERS = (
    "GREENHOUSE",
    "WORKDAY",
    "NAUKRI",
    "INDEED",
    "LEVER",
    "ASHBY",
    "RIPPLING",
    "ICIMS",
    "BRASSRING",
    "BAMBOOHR",
    "WORKABLE",
    "JAZZHR",
    "JOBVITE",
    "BREEZYHR",
    "ORACLE_RECRUITING",
    "PAYLOCITY",
    "SMARTRECRUITERS",
    "UKG_ULTIPRO",
    "ZOHO_RECRUIT",
    "ADP",
    "DOVER",
    "GEM",
    "SAP_SUCCESSFACTORS",
    "RECRUITEE",
    "PINPOINT",
    "TEAMTAILOR",
    "POLYMER",
    "PHENOM",
    "DAYFORCE",
    "JOIN",
    "CAREERPLUG",
    "HIREOLOGY",
)

RESUME_BYTES = (
    b"%PDF-1.4\n% MUNSHI controlled ATS parity fixture\n"
    b"1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
)
RESUME_SHA = hashlib.sha256(RESUME_BYTES).hexdigest()


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


def _plan(provider: str, url: str) -> dict:
    return {
        "job": {
            "id": "fixture-job-001",
            "company": "MUNSHI Synthetic Employer",
            "title": "People Analytics Specialist",
            "job_url": url,
            "apply_url": url,
        },
        "provider_policy": {"provider": provider, "permitted": True},
        "resume": {
            "artifact_id": "fixture-resume-artifact",
            "version_id": "fixture-resume-version",
            "version_number": 1,
            "filename": "munshi-fixture-resume.pdf",
            "mime_type": "application/pdf",
            "artifact_sha256": RESUME_SHA,
        },
        "answers": [
            {
                "question_key": "first_name",
                "normalized_question": "First name",
                "autofill_allowed": True,
                "sensitivity_class": "NORMAL",
                "execution_value": "Aadil",
            },
            {
                "question_key": "last_name",
                "normalized_question": "Last name",
                "autofill_allowed": True,
                "sensitivity_class": "NORMAL",
                "execution_value": "Munshi",
            },
        ],
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
        },
    }


def test_all_screenshot_ats_families_use_shared_verified_browser_engine(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    runtime = _root() / "apps/native-host/browser-dist/plan-runtime.js"
    fixture = (
        _root()
        / "apps/native-host/tests/browser/fixtures/greenhouse_like_application.html"
    )
    assert runtime.is_file()
    html = fixture.read_text()

    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            executable_path=resolve_browser_executable(),
        )
        for provider in SCREENSHOT_PROVIDERS:
            domain = KNOWN_PROVIDER_RECIPES[provider][0]
            url = f"https://jobs.{domain}/munshi-fixture/jobs/fixture-job-001"
            plan = _plan(provider, url)
            page = browser.new_page()

            def handler(route, expected_url=url) -> None:
                request = route.request
                if request.url == expected_url and request.method == "GET":
                    route.fulfill(
                        status=200,
                        content_type="text/html",
                        body=html,
                    )
                else:
                    route.abort()

            page.route("**/*", handler)
            page.goto(url, wait_until="domcontentloaded")
            adapter = PlanBrowserAdapter(
                page,
                artifact_reader=lambda current: RESUME_BYTES,
                current_plan=lambda current, expected=plan: current == expected,
                runtime_path=runtime,
            )
            inspected = adapter.inspect_job(plan=plan)
            prepared = adapter.prepare_form(
                plan=plan,
                checkpoint=None,
                resolved_values={},
            )

            assert provider_for_url(url) == provider
            assert inspected["provider"] == provider
            assert inspected["provider_recipe"] == provider
            assert prepared["provider"] == provider
            assert prepared["resume_uploaded"] is True
            assert prepared["resume_sha256"] == RESUME_SHA
            assert (
                prepared["completed_required_fields"]
                == prepared["required_fields"]
            )
            assert prepared["unresolved"] == []
            assert prepared["validation_errors"] == []
            assert page.locator("#first_name").input_value() == "Aadil"
            assert page.locator("#last_name").input_value() == "Munshi"

            described = page.evaluate("MunshiPlanRuntime.describeForm()")
            final_submit = [
                item
                for item in described["page"]["navigationCandidates"]
                if item["action"] == "FINAL_SUBMIT"
            ]
            assert len(final_submit) == 1
            refused = page.evaluate(
                "id => MunshiPlanRuntime.applyNavigationAction(id)",
                final_submit[0]["controlId"],
            )
            assert refused["status"] == "REFUSED"
            assert page.locator("#application-form").is_visible()
            assert not page.locator("#application_confirmation").is_visible()
            page.close()
        browser.close()


def test_screenshot_provider_matrix_is_complete() -> None:
    assert len(SCREENSHOT_PROVIDERS) == 32
    assert set(SCREENSHOT_PROVIDERS).issubset(KNOWN_PROVIDER_RECIPES)
