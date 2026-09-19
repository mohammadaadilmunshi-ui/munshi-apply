from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

from munshi_apply_native.browser_runtime import resolve_browser_executable  # noqa: E402
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")

JOB_URL = "https://boards.greenhouse.io/munshi-fixture/jobs/fixture-job-001"
SUBMIT_URL = "https://boards.greenhouse.io/munshi-fixture/applications"
TELEMETRY_URL = "https://boards.greenhouse.io/munshi-fixture/telemetry"
RESUME_BYTES = (
    b"%PDF-1.4\n% MUNSHI controlled browser fixture only\n"
    b"1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
)
RESUME_SHA = hashlib.sha256(RESUME_BYTES).hexdigest()


@pytest.fixture(autouse=True)
def _enable_prepare_actions(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


def _plan() -> dict:
    return {
        "job": {
            "id": "fixture-job-001",
            "company": "MUNSHI Synthetic Employer",
            "title": "People Analytics Specialist",
            "job_url": JOB_URL,
            "apply_url": JOB_URL,
        },
        "provider_policy": {"provider": "GREENHOUSE"},
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


def _adapter(page, plan):
    runtime = _root() / "apps/native-host/browser-dist/plan-runtime.js"
    assert runtime.is_file(), "run npm run build before the real-browser lane"
    return PlanBrowserAdapter(
        page,
        artifact_reader=lambda current: RESUME_BYTES,
        current_plan=lambda current: current == plan,
        runtime_path=runtime,
    )


def _route(
    page,
    html: str,
    *,
    correlated: bool,
    weak_application_id: bool = False,
) -> None:
    def handler(route):
        request = route.request
        if request.url == JOB_URL and request.method == "GET":
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        if request.url == TELEMETRY_URL and request.method == "POST":
            payload = {
                "status": "submitted",
                "job_id": "fixture-job-001",
                "application_id": "FAKE-TELEMETRY-ID",
            }
            route.fulfill(
                status=201,
                content_type="application/json",
                body=json.dumps(payload),
            )
            return
        if request.url == SUBMIT_URL and request.method == "POST":
            if weak_application_id:
                payload = {
                    "status": "created",
                    "job_id": "fixture-job-001",
                    "id": "generic-object-id",
                }
            else:
                payload = (
                    {
                        "status": "submitted",
                        "job_id": "fixture-job-001",
                        "application_id": "fixture-application-001",
                    }
                    if correlated
                    else {"status": "submitted"}
                )
            route.fulfill(
                status=201,
                content_type="application/json",
                body=json.dumps(payload),
            )
            return
        route.abort()

    page.route("**/*", handler)


def _review(prepared: dict) -> dict:
    return {
        "destination_url": JOB_URL,
        "browser_verification": {"form_digest": prepared["form_digest"]},
    }


def _prepare(
    page,
    *,
    correlated: bool,
    include_telemetry: bool = False,
    weak_application_id: bool = False,
):
    plan = _plan()
    fixture = (
        _root()
        / "apps/native-host/tests/browser/fixtures/greenhouse_like_application.html"
    )
    html = fixture.read_text()
    if include_telemetry:
        original = 'await fetch("/munshi-fixture/applications", {'
        injected = """await fetch("/munshi-fixture/telemetry", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  job_id: "fixture-job-001",
                  event: "submit-clicked",
                }),
              });
              await fetch("/munshi-fixture/applications", {"""
        html = html.replace(original, injected, 1)
    _route(page, html, correlated=correlated, weak_application_id=weak_application_id)
    page.goto(JOB_URL, wait_until="domcontentloaded")
    adapter = _adapter(page, plan)
    prepared = adapter.prepare_form(plan=plan, checkpoint=None, resolved_values={})
    return plan, adapter, prepared


def test_real_chrome_prepares_exact_artifact_and_generic_navigation_refuses_submit():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan, adapter, prepared = _prepare(page, correlated=True)

        assert prepared["provider"] == "GREENHOUSE"
        assert prepared["job_id"] == "fixture-job-001"
        assert prepared["resume_uploaded"] is True
        assert prepared["resume_sha256"] == RESUME_SHA
        assert prepared["completed_required_fields"] == prepared["required_fields"]
        assert prepared["unresolved"] == []
        assert prepared["validation_errors"] == []
        assert page.locator("#first_name").input_value() == "Aadil"
        assert page.locator("#last_name").input_value() == "Munshi"

        described = page.evaluate("MunshiPlanRuntime.describeForm()")
        final_submit = [
            item for item in described["page"]["navigationCandidates"]
            if item["action"] == "FINAL_SUBMIT"
        ]
        assert len(final_submit) == 1
        generic = page.evaluate(
            "id => MunshiPlanRuntime.applyNavigationAction(id)", final_submit[0]["controlId"]
        )
        assert generic["status"] == "REFUSED"
        assert page.locator("#application-form").is_visible()
        assert not page.locator("#application_confirmation").is_visible()
        browser.close()


def test_real_chrome_uploads_resume_to_hidden_native_file_input():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan = _plan()
        fixture = (
            _root()
            / "apps/native-host/tests/browser/fixtures/greenhouse_like_application.html"
        )
        html = fixture.read_text().replace(
            'id="resume"\n            name="resume"',
            'id="resume"\n            style="display:none"\n            name="resume"',
            1,
        )
        _route(page, html, correlated=True)
        page.goto(JOB_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)

        scanned = adapter._scan()
        resume_control = next(
            control
            for control in scanned["page"]["controls"]
            if control.get("inputType") == "file"
        )
        assert resume_control["visible"] is False
        assert "resume" in str(resume_control.get("label") or "").casefold()

        prepared = adapter.prepare_form(
            plan=plan,
            checkpoint=None,
            resolved_values={},
        )

        assert prepared["resume_uploaded"] is True
        assert prepared["resume_sha256"] == RESUME_SHA
        assert page.locator("#resume").evaluate(
            "element => element.files && element.files.length"
        ) == 1
        browser.close()


def test_dedicated_submit_requires_correlated_provider_response_for_verified():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan, adapter, prepared = _prepare(page, correlated=True)
        result = adapter.submit(plan=plan, review=_review(prepared))

        assert result["action_executed"] is True
        assert result["verification_status"] == "VERIFIED"
        assert result["provider_application_id"] == "fixture-application-001"
        evidence = result["success_evidence"]
        assert evidence["provider"] == "GREENHOUSE"
        assert evidence["job_id"] == "fixture-job-001"
        assert evidence["provider_application_id"] == "fixture-application-001"
        assert evidence["response_status"] == 201
        assert evidence["submission_response_marker"] == "exact-approved-action-response"
        assert evidence["exact_action_verified"] is True
        assert evidence["post_submit_state_changed"] is True
        browser.close()


def test_exact_action_and_confirmation_verify_without_provider_specific_application_id():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan, adapter, prepared = _prepare(page, correlated=False)
        result = adapter.submit(plan=plan, review=_review(prepared))

        assert result["action_executed"] is True
        assert result["verification_status"] == "VERIFIED"
        assert result["provider_application_id"].startswith("submission-ref-")
        assert result["success_evidence"]["provider_application_id_source"] == (
            "DERIVED_EXACT_ACTION_EVIDENCE"
        )
        browser.close()


def test_unrelated_same_provider_post_does_not_replace_exact_submit_evidence():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan, adapter, prepared = _prepare(
            page, correlated=False, include_telemetry=True
        )
        result = adapter.submit(plan=plan, review=_review(prepared))

        assert result["action_executed"] is True
        assert result["verification_status"] == "VERIFIED"
        assert result["provider_application_id"].startswith("submission-ref-")
        assert result["success_evidence"]["response_url"] == SUBMIT_URL
        browser.close()


def test_form_action_and_method_are_bound_into_review_digest():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan, adapter, prepared = _prepare(page, correlated=True)

        before = prepared["form_digest"]
        binding = prepared["submit_binding"]
        assert binding["binding_type"] == "NATIVE_FORM"
        assert binding["action"] == SUBMIT_URL
        assert binding["method"] == "POST"
        assert len(binding["binding_digest"]) == 64
        assert binding["control_id"]
        page.locator("#application-form").evaluate(
            """form => {
              form.action = '/munshi-fixture/changed-submit';
              form.method = 'get';
            }"""
        )
        changed = adapter.inspect_submission(plan=plan)

        assert changed["form_digest"] != before
        assert changed["submit_binding"] != prepared["submit_binding"]
        with pytest.raises(ValueError, match="Browser form changed after review"):
            adapter.submit(plan=plan, review=_review(prepared))
        assert page.locator("#application-form").is_visible()
        browser.close()


def test_generic_created_response_uses_derived_exact_action_reference():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan, adapter, prepared = _prepare(
            page, correlated=False, weak_application_id=True
        )
        result = adapter.submit(plan=plan, review=_review(prepared))

        assert result["action_executed"] is True
        assert result["verification_status"] == "VERIFIED"
        assert result["provider_application_id"].startswith("submission-ref-")
        assert result["success_evidence"]["provider_application_id_source"] == (
            "DERIVED_EXACT_ACTION_EVIDENCE"
        )
        browser.close()


def test_submit_target_race_after_final_observation_is_blocked_before_click():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan, adapter, prepared = _prepare(page, correlated=True)
        original_inspect = adapter.inspect_submission
        calls = 0

        def racing_inspect(*, plan):
            nonlocal calls
            observation = original_inspect(plan=plan)
            calls += 1
            if calls == 2:
                page.locator("#application-form").evaluate(
                    "form => { form.action = '/munshi-fixture/changed-submit'; }"
                )
            return observation

        adapter.inspect_submission = racing_inspect
        result = adapter.submit(plan=plan, review=_review(prepared))

        assert result == {"action_executed": False, "verification_status": "BLOCKED"}
        assert page.locator("#application-form").is_visible()
        assert not page.locator("#application_confirmation").is_visible()
        browser.close()


UNKNOWN_JOB_URL = "https://jobs.unknown-ats.example/apply/fixture-job-777"
UNKNOWN_SUBMIT_URL = "https://jobs.unknown-ats.example/api/applications/fixture-job-777"


def _unknown_provider_plan() -> dict:
    return {
        "job": {
            "id": "fixture-job-777",
            "company": "Unknown ATS Fixture",
            "title": "People Data Analyst",
            "job_url": UNKNOWN_JOB_URL,
            "apply_url": UNKNOWN_JOB_URL,
        },
        "provider_policy": {
            "provider": "GENERIC",
            "permitted": True,
            "allowed_hosts": ["unknown-ats.example"],
        },
        "resume": {
            "artifact_id": "fixture-resume-artifact",
            "version_id": "fixture-resume-version",
            "version_number": 1,
            "filename": "munshi-fixture-resume.pdf",
            "mime_type": "application/pdf",
            "artifact_sha256": RESUME_SHA,
        },
        "answers": [],
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
        },
    }


def _unknown_provider_html() -> str:
    return """<!doctype html>
<html>
<body>
  <main>
    <h1>People Data Analyst</h1>
    <label for="resume">Resume</label>
    <input id="resume" name="resume" type="file" required />
    <button
      id="send-application"
      type="button"
      data-submit-url="/api/applications/fixture-job-777"
      data-method="PUT"
      aria-label="Submit application"
    >Submit application</button>
    <section id="application_confirmation" hidden role="status">
      Application received. Thank you for applying.
    </section>
  </main>
  <script>
    document.querySelector("#send-application").addEventListener("click", async () => {
      const response = await fetch("/api/applications/fixture-job-777", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({job_id: "fixture-job-777"}),
      });
      if (response.ok) {
        document.querySelector("#send-application").remove();
        document.querySelector("#application_confirmation").hidden = false;
      }
    });
  </script>
</body>
</html>"""


def test_unknown_provider_uses_generic_dom_and_declarative_put_submit_binding():
    browser_path = resolve_browser_executable()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        plan = _unknown_provider_plan()

        def handler(route):
            request = route.request
            if request.url == UNKNOWN_JOB_URL and request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=_unknown_provider_html(),
                )
                return
            if request.url == UNKNOWN_SUBMIT_URL and request.method == "PUT":
                route.fulfill(
                    status=202,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "submitted",
                            "job_id": "fixture-job-777",
                        }
                    ),
                )
                return
            route.abort()

        page.route("**/*", handler)
        page.goto(UNKNOWN_JOB_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)

        prepared = adapter.prepare_form(
            plan=plan,
            checkpoint=None,
            resolved_values={},
        )

        assert prepared["provider"] == "GENERIC"
        assert prepared["provider_recipe"] == "GENERIC"
        assert prepared["job_id"] == "fixture-job-777"
        assert prepared["resume_uploaded"] is True
        binding = prepared["submit_binding"]
        assert binding["binding_type"] == "DECLARATIVE_CONTROL"
        assert binding["method"] == "PUT"
        assert binding["action"] == UNKNOWN_SUBMIT_URL
        assert binding["control_id"]

        result = adapter.submit(
            plan=plan,
            review={
                "destination_url": UNKNOWN_JOB_URL,
                "browser_verification": {"form_digest": prepared["form_digest"]},
            },
        )

        assert result["action_executed"] is True
        assert result["verification_status"] == "VERIFIED"
        assert result["provider_application_id"].startswith("submission-ref-")
        evidence = result["success_evidence"]
        assert evidence["provider"] == "GENERIC"
        assert evidence["provider_recipe"] == "GENERIC"
        assert evidence["submit_method"] == "PUT"
        assert evidence["submit_action"] == UNKNOWN_SUBMIT_URL
        assert evidence["response_url"] == UNKNOWN_SUBMIT_URL
        assert evidence["exact_action_verified"] is True
        assert evidence["post_submit_state_changed"] is True
        browser.close()
