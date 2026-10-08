from __future__ import annotations

import os

import pytest
from playwright.sync_api import sync_playwright
from test_workday_multiselect_ancestor_chrome import (
    RESUME_BYTES,
    _fixture_html,
    _plan,
    _root,
    _route,
)

from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1", reason="browser opt in"
)


def test_crescent_referral_and_phone_select_on_same_workday_page(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    plan = _plan()
    plan["answers"].append(
        {
            "question_key": "phonetype",
            "normalized_question": "Phone Device Type Select One Required",
            "sensitivity_class": "NORMAL",
            "autofill_allowed": True,
            "execution_value": "Mobile",
        }
    )
    # The text, name and id are those from the observed Crescent checkpoint;
    # the option markup here is a synthetic native-select variant.
    addition = """<label for="phoneNumber--phoneType">Phone Device Type Select One Required</label>
    <select id="phoneNumber--phoneType" name="phoneType" required>
      <option value="">Select One</option><option value="Mobile">Mobile</option>
      <option value="Home">Home</option>
    </select>"""
    html = _fixture_html().replace(
        '<button id="fixture-submit"', addition + '<button id="fixture-submit"'
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=resolve_browser_executable())
        page = browser.new_page()
        _route(page, html)
        page.goto(plan["job"]["apply_url"], wait_until="domcontentloaded")
        adapter = PlanBrowserAdapter(
            page,
            artifact_reader=lambda _plan: RESUME_BYTES,
            current_plan=lambda candidate: candidate is plan,
            runtime_path=_root() / "apps/native-host/browser-dist/plan-runtime.js",
        )
        described = adapter._scan()["page"]
        control_ids = [x["controlId"] for x in described["questions"]]
        assert len(control_ids) >= 2
        prepared = adapter.prepare_form(plan=plan, checkpoint=None, resolved_values={})
        assert prepared["unresolved"] == [], prepared
        assert (
            page.evaluate("() => document.getElementById('phoneNumber--phoneType').value")
            == "Mobile"
        )
        assert (
            page.locator('[data-automation-id="selectedItem-referral"]').inner_text().strip()
            == "Indeed"
        )
        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        browser.close()
