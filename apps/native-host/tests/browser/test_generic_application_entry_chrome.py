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
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")

JOB_URL = "https://jobs.generic.example/roles/fixture-1"
RESUME_BYTES = (
    b"%PDF-1.4\n% provider-neutral controlled fixture\n"
    b"1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
)
RESUME_SHA = hashlib.sha256(RESUME_BYTES).hexdigest()


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_generic_entry_ignores_hidden_template_file_then_uploads_cv(monkeypatch) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    html = """<!doctype html>
<html>
<body>
  <main>
    <h1>People Analytics Fixture</h1>
    <label for="cv-upload">CV</label>
    <input id="cv-upload" type="file" accept=".pdf" style="display:none" />
    <button id="apply-entry" type="button">Apply Now</button>
    <section id="application" hidden>
      <label for="first-name">First name</label>
      <input id="first-name" name="first_name" type="text" required />
      <button id="submit-application" type="submit">Submit application</button>
    </section>
  </main>
  <script>
    document.querySelector("#apply-entry").addEventListener("click", () => {
      document.querySelector("#apply-entry").remove();
      document.querySelector("#application").hidden = false;
    });
  </script>
</body>
</html>"""
    plan = {
        "plan_id": "plan-generic-entry",
        "job": {
            "id": "fixture-1",
            "company": "Synthetic Generic Employer",
            "title": "People Analytics Fixture",
            "job_url": JOB_URL,
            "apply_url": JOB_URL,
        },
        "provider_policy": {
            "provider": "GENERIC",
            "permitted": True,
            "allowed_hosts": ["jobs.generic.example"],
        },
        "resume": {
            "artifact_id": "resume-artifact",
            "version_id": "resume-version",
            "version_number": 1,
            "filename": "resume.pdf",
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

    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            executable_path=resolve_browser_executable(),
        )
        page = browser.new_page()

        def route_handler(route):
            if route.request.url == JOB_URL and route.request.method == "GET":
                route.fulfill(status=200, content_type="text/html", body=html)
            else:
                route.abort()

        page.route("**/*", route_handler)
        page.goto(JOB_URL, wait_until="domcontentloaded")
        runtime = _root() / "apps/native-host/browser-dist/plan-runtime.js"
        assert runtime.is_file(), "run npm run build before the real-browser lane"
        adapter = PlanBrowserAdapter(
            page,
            artifact_reader=lambda _plan: RESUME_BYTES,
            current_plan=lambda current: current == plan,
            runtime_path=runtime,
        )

        prepared = adapter.prepare_form(
            plan=plan,
            checkpoint=None,
            resolved_values={"first_name": "Aadil"},
        )

        assert page.locator("#apply-entry").count() == 0
        assert page.locator("#first-name").input_value() == "Aadil"
        assert prepared["resume_uploaded"] is True
        assert prepared["resume_sha256"] == RESUME_SHA
        assert prepared["unresolved"] == []
        assert prepared["validation_errors"] == []
        browser.close()
