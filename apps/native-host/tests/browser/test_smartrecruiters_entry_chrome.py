from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)
BASE = "https://jobs.smartrecruiters.com/DohlerGmbH/744000154149608-human-resources-coordinator"
ENTRY = (
    "https://jobs.smartrecruiters.com/oneclick-ui/company/DohlerGmbH/"
    "publication/925695ab-68a9-4300-8c29-e68da157aefc?dcr_ci=DohlerGmbH"
)
PDF = b"%PDF-1.4\nsynthetic test resume\n%%EOF\n"


def _browser():
    pw = pytest.importorskip("playwright.sync_api").sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True, executable_path=resolve_browser_executable()
    )
    return pw, browser


def _setup(page, *, status=200):
    listing = (
        '<html><body><h1>Human Resources Coordinator</h1>'
        + ''.join(f'<a href="{ENTRY}">I&apos;m interested</a>' for _ in range(3))
        + '</body></html>'
    )
    form = (
        '<html><body><label for="resume">Resume / CV</label>'
        '<input id="resume" type="file" name="resume"></body></html>'
    )

    def handle(route):
        url = route.request.url
        if "/oneclick-ui/" in url:
            route.fulfill(
                status=status,
                body=form if status == 200 else "Access temporarily restricted",
                content_type="text/html",
            )
        elif url == BASE:
            route.fulfill(status=200, body=listing, content_type="text/html")
        else:
            route.abort()

    page.route("**/*", handle)
    page.goto(BASE)


def _adapter(page):
    plan = {
        "plan_id": "test-plan",
        "job": {"id": "6198", "apply_url": BASE},
        "resume": {
            "filename": "resume.pdf",
            "mime_type": "application/pdf",
            "artifact_sha256": hashlib.sha256(PDF).hexdigest(),
        },
    }
    adapter = PlanBrowserAdapter(
        page,
        current_plan=lambda _plan: True,
        artifact_reader=lambda _plan: PDF,
        runtime_path=Path("/nonexistent-js-never-scanned-here"),
    )
    return adapter, plan


def test_smartrecruiters_entry_then_browser_hashed_resume(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    pw, browser = _browser()
    try:
        page = browser.new_page()
        _setup(page)
        adapter, plan = _adapter(page)
        assert adapter._advance_application_entry_surface(plan) is True
        assert page.url == ENTRY
        evidence = adapter._universal_document_upload(
            plan=plan, permissions={"resume_upload": True}
        )
        assert evidence == {"resume": hashlib.sha256(PDF).hexdigest()}
        assert page.locator('input[type="file"]').evaluate("e => e.files.length") == 1
    finally:
        browser.close()
        pw.stop()


def test_smartrecruiters_403_refuses_entry_and_upload():
    pw, browser = _browser()
    try:
        page = browser.new_page()
        _setup(page, status=403)
        adapter, plan = _adapter(page)
        with pytest.raises(ValueError, match="entry restricted"):
            adapter._advance_application_entry_surface(plan)
        assert adapter._verified_smartrecruiters_entry is None
    finally:
        browser.close()
        pw.stop()
