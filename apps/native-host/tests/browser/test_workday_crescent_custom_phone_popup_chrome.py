from __future__ import annotations
import os
from pathlib import Path
import pytest
pytestmark = pytest.mark.skipif(os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1", reason="browser opt in")
from playwright.sync_api import sync_playwright
from munshi_apply_native.browser_runtime import resolve_browser_executable
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter
from test_workday_multiselect_ancestor_chrome import _plan, _route, _fixture_html, _root, RESUME_BYTES

def test_crescent_realistic_phone_device_popup_and_referral(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    plan = _plan()
    plan["answers"].append({
        "question_key": "phonetype",
        "normalized_question": "Phone Device Type Select One Required",
        "sensitivity_class": "NORMAL", "autofill_allowed": True,
        "execution_value": "Mobile"
    })
    # Synthetic button/dropdown variant, matching the observed live ID/name/label.
    addition = '''<section data-automation-id="phone">
      <label id="phone-label">Phone Device Type Select One Required</label>
      <button type="button" id="phoneNumber--phoneType" name="phoneType"
              aria-labelledby="phone-label" aria-haspopup="listbox" aria-expanded="false"
              aria-controls="phone-type-options">Select One</button>
      <div role="listbox" id="phone-type-options" hidden>
        <div role="option" data-automation-id="dropdownOption">Mobile</div>
        <div role="option" data-automation-id="dropdownOption">Home</div>
      </div>
      <script>
      document.getElementById('phoneNumber--phoneType').addEventListener('click', () => {
         let list = document.getElementById('phone-type-options');
         list.hidden = !list.hidden;
         document.getElementById('phoneNumber--phoneType').setAttribute('aria-expanded',String(!list.hidden));
      });
      document.querySelectorAll('#phone-type-options [role="option"]').forEach(option => {
         option.addEventListener('click',()=>{
            let button = document.getElementById('phoneNumber--phoneType');
            button.textContent = option.textContent;
            button.setAttribute('data-selected-value',option.textContent);
            document.getElementById('phone-type-options').hidden=true;
         });
      });
      </script>
    </section>'''
    # Nested scripts allowed in fixture browser.
    html = _fixture_html().replace('<button id="fixture-submit"', addition + '<button id="fixture-submit"')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=resolve_browser_executable())
        page = browser.new_page()
        _route(page, html)
        page.goto(plan["job"]["apply_url"],wait_until="domcontentloaded")
        adapter = PlanBrowserAdapter(page,artifact_reader=lambda _: RESUME_BYTES,
          current_plan=lambda candidate: candidate is plan,
          runtime_path=_root()/"apps/native-host/browser-dist/plan-runtime.js")
        fields=adapter._scan()
        prepared=adapter.prepare_form(plan=plan, checkpoint=None,resolved_values={})
        assert prepared["unresolved"]==[], prepared
        assert page.locator("#phoneNumber--phoneType").inner_text().strip()=="Mobile"
        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        browser.close()
