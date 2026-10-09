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

WORKDAY_URL = (
    "https://crescentfixture.wd108.myworkdayjobs.com/en-US/crescent_energy_careers/"
    "job/Houston-TX/HR-Analyst---Total-Rewards_R441/apply"
)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
RESUME_BYTES = (
    b"%PDF-1.4\n% MUNSHI Crescent referral fixture\n"
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
        "version": "munshi-application-plan-v2",
        "application_id": "application-workday-crescent-fixture",
        "plan_id": "application-plan-workday-crescent-fixture",
        "plan_digest": "c" * 64,
        "job": {
            "id": "fixture-job-4465",
            "company": "Crescent Fixture Energy",
            "title": "HR Analyst - Total Rewards",
            "job_url": WORKDAY_URL,
            "apply_url": WORKDAY_URL,
        },
        "provider_policy": {
            "provider": "WORKDAY",
            "permitted": True,
            "allowed_hosts": ["myworkdayjobs.com"],
        },
        "resume": {
            "artifact_id": "fixture-resume",
            "version_id": "fixture-resume-version",
            "filename": "fixture-resume.pdf",
            "mime_type": "application/pdf",
            "artifact_sha256": RESUME_SHA,
        },
        "answers": [
            {
                "question_key": "q-ctl-h9otse",
                "normalized_question": "How Did You Hear About Us?*",
                "sensitivity_class": "NORMAL",
                "autofill_allowed": True,
                "execution_value": "Indeed",
            }
        ],
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
        },
        "submission_authority": False,
    }


def _route(page, html: str) -> None:
    def handler(route):
        if route.request.url == WORKDAY_URL and route.request.method == "GET":
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        route.abort()

    page.route("**/*", handler)


def _fixture_html() -> str:
    return (
        _root()
        / "apps/native-host/tests/browser/fixtures/"
        / "workday_crescent_referral_multiselect.html"
    ).read_text(encoding="utf-8")


def _adapter(page, plan) -> PlanBrowserAdapter:
    runtime = _root() / "apps/native-host/browser-dist/plan-runtime.js"
    assert runtime.is_file(), "run npm run build before the real-browser lane"
    return PlanBrowserAdapter(
        page,
        artifact_reader=lambda current: RESUME_BYTES,
        current_plan=lambda current: current is plan,
        runtime_path=runtime,
    )


def _referral_field(described: dict) -> dict:
    for field in described.get("fields") or []:
        observation = field.get("question_observation") or {}
        if str(observation.get("id") or "") == "source--source":
            return field
    raise AssertionError("referral field source--source was not described")


def _referral_control_and_question(adapter: PlanBrowserAdapter):
    described = adapter._scan()
    page = described["page"]
    for question in page.get("questions") or []:
        if "How Did You Hear About Us" in str(question.get("rawText") or ""):
            for control in page.get("controls") or []:
                if str(control.get("controlId")) == str(
                    question.get("controlId")
                ):
                    return control, question
    raise AssertionError("referral control and question were not described")


def test_crescent_referral_routes_through_existing_prompt_machinery():
    """The exact observed Crescent DOM must classify as a Workday prompt.

    The input carries NO role, NO aria-haspopup, NO aria-autocomplete, NO
    data-automation-id and NO name; Workday's component identity lives only on
    the multiselectInputContainer / multiSelectContainer ancestor wrappers.
    """
    browser_path = resolve_browser_executable()
    plan = _plan()

    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, _fixture_html())
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)

        control, question = _referral_control_and_question(adapter)
        assert str(control.get("kind") or "").upper() == "TEXT"

        element = page.evaluate_handle(
            "id => MunshiPlanRuntime.element(id)", control["controlId"]
        ).as_element()
        assert element is not None

        # The existing exact-option machinery must run for this control and the
        # provider-selected state must verify: typed filter text alone is not a
        # committed value.
        result = adapter._workday_fill_control(
            control=control, question=question, value="Indeed"
        )
        assert result["status"] == "FILLED"
        assert result["strategy"] == "WORKDAY_PROVIDER_PROMPT"
        assert result["verification"] == "POST_ACTION_PROVIDER_VERIFIED"

        # Workday discards the typed filter text; the selected item is the truth.
        assert page.evaluate(
            "() => document.getElementById('source--source').value"
        ) == ""
        chip = page.locator('[data-automation-id="selectedItem-referral"]')
        assert chip.count() == 1
        assert chip.inner_text().strip() == "Indeed"

        # The scanner-side verifier must report the provider-selected value and
        # treat it as satisfied only through that provider-backed value.
        field = _referral_field(adapter._scan())
        assert field["satisfied"] is True
        assert field["display_value"] == "Indeed"

        # No submit occurred.
        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        assert page.locator("body").get_attribute("data-submitted") is None
        browser.close()


def test_crescent_referral_prepare_form_completes_without_submit():
    browser_path = resolve_browser_executable()
    plan = _plan()

    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, _fixture_html())
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)

        prepared = adapter.prepare_form(
            plan=plan,
            checkpoint=None,
            resolved_values={},
        )

        assert prepared["unresolved"] == []
        assert prepared["validation_errors"] == []
        trace = prepared["field_action_evidence"]
        assert any(
            item["semantic_type"] == "REFERRAL"
            and item["status"] == "FILLED"
            and item["strategy"] == "WORKDAY_PROVIDER_PROMPT"
            and item["plan_match_count"] == 1
            for item in trace
        ), trace
        assert "Indeed" not in repr(trace)
        field = _referral_field(adapter._scan())
        assert field["satisfied"] is True

        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        assert page.evaluate("() => window.__fixtureNextClicked") is False
        assert page.locator("body").get_attribute("data-submitted") is None
        browser.close()


def test_crescent_referral_fails_closed_without_provider_selected_state():
    """Without a provider-selected item the fill must fail closed.

    Typed filter text alone must never mark the field satisfied, in either the
    adapter fill result or the scanner-side verifier.
    """
    browser_path = resolve_browser_executable()
    plan = _plan()

    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, _fixture_html())
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        page.evaluate("() => { window.__fixtureFailSelection = true; }")
        adapter = _adapter(page, plan)

        control, question = _referral_control_and_question(adapter)
        result = adapter._workday_fill_control(
            control=control, question=question, value="Indeed"
        )
        assert result["status"] == "FAILED"
        assert result["verification"] == "FAILED_CLOSED"

        # Typed text present in the input with no provider-selected item must
        # still never count as a committed value.
        page.evaluate(
            """() => {
              const input = document.getElementById('source--source');
              input.value = 'Indeed';
              input.dispatchEvent(new Event('input', { bubbles: true }));
            }"""
        )
        field = _referral_field(adapter._scan())
        assert field["satisfied"] is False
        assert field["value_digest"] == EMPTY_SHA256
        assert (
            page.evaluate(
                "() => document.getElementById('source--source').value"
            )
            == "Indeed"
        )

        prepared = adapter.prepare_form(
            plan=plan,
            checkpoint=None,
            resolved_values={},
        )
        assert prepared["unresolved"] != []
        trace = prepared["field_action_evidence"]
        assert any(
            item["semantic_type"] == "REFERRAL"
            and item["status"] == "FAILED"
            and item["verification"] == "FAILED_CLOSED"
            for item in trace
        ), trace
        assert "Indeed" not in repr(trace)

        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        assert page.locator("body").get_attribute("data-submitted") is None
        browser.close()


def test_crescent_referral_with_removable_selected_chip():
    """Real Workday displays a remove icon beside the selected 'Indeed' chip.

    A provider-backed choice can have non-value text in the selectedItem
    wrapper. Never use the filter input alone to declare success.
    """
    browser_path = resolve_browser_executable()
    plan = _plan()
    html = _fixture_html().replace(
        "chip.textContent = value;",
        """chip.innerHTML = '<button type="button" aria-label="Remove"'
          + ' data-automation-id="removeItem">×</button>'
          + '<span data-automation-id="selectedItemLabel">' + value + '</span>';""",
    )
    assert html != _fixture_html()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, html)
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)
        control, question = _referral_control_and_question(adapter)
        result = adapter._workday_fill_control(
            control=control, question=question, value="Indeed"
        )
        assert result["status"] == "FILLED", result
        assert result["verification"] == "POST_ACTION_PROVIDER_VERIFIED"
        assert page.locator('[data-automation-id="removeItem"]').count() == 1
        assert page.locator('[data-automation-id="selectedItemLabel"]').inner_text() == "Indeed"
        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        browser.close()


def test_crescent_referral_nested_duplicate_option_is_one_choice():
    """One provider option may match two nested selectors in the DOM.

    This must still be one exact option; distinct real choices remain
    ambiguous and fail closed.
    """
    browser_path = resolve_browser_executable()
    plan = _plan()
    html = _fixture_html().replace(
        "                Indeed\n              </div>",
        '                <span data-option-value="Indeed">Indeed</span>\n              </div>',
        1,
    )
    assert html != _fixture_html()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, html)
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)
        control, question = _referral_control_and_question(adapter)
        result = adapter._workday_fill_control(
            control=control, question=question, value="Indeed"
        )
        assert result["status"] == "FILLED", result
        assert result["verification"] == "POST_ACTION_PROVIDER_VERIFIED"
        assert page.locator('[data-automation-id="selectedItem-referral"]').count() == 1
        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        browser.close()


def test_crescent_two_distinct_exact_referral_options_fail_closed():
    """DOM deduplication cannot silently merge two distinct provider options."""
    browser_path = resolve_browser_executable()
    plan = _plan()
    html = _fixture_html().replace(
        'data-option-id="linkedin"',
        'data-option-id="alternate-indeed"',
        1,
    ).replace('                LinkedIn\n', '                Indeed\n', 1)
    assert html != _fixture_html()
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, html)
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)
        control, question = _referral_control_and_question(adapter)
        result = adapter._workday_fill_control(
            control=control, question=question, value="Indeed"
        )
        assert result["status"] == "FAILED", result
        assert result["verification"] == "FAILED_CLOSED"
        assert page.locator('[data-automation-id^="selectedItem"]').count() == 0
        assert page.evaluate("() => window.__fixtureSubmitClicked") is False
        browser.close()


def test_crescent_referral_opens_exactly_one_scoped_chooser_before_selecting():
    """An icon-gated popup must open without any blind Enter/Submit action."""
    browser_path = resolve_browser_executable()
    plan = _plan()
    html = _fixture_html()
    html = html.replace(
        '<div id="referral-options" hidden>',
        '<button type="button" id="open-chooser" '
        'data-automation-id="promptIcon">Choose</button>'
        '<div id="referral-options" hidden>',
        1,
    )
    html = html.replace(
        '      const refreshOptions = () => {',
        '      window.__fixtureChooserOpen = false;\n'
        '      const refreshOptions = () => {',
        1,
    )
    html = html.replace(
        '              query &&',
        '              window.__fixtureChooserOpen && query &&',
        1,
    )
    html = html.replace(
        '      input.addEventListener("input", refreshOptions);',
        '''      document.getElementById("open-chooser")
          .addEventListener("click", () => {
            window.__fixtureChooserOpen = true;
            refreshOptions();
          });
      input.addEventListener("input", refreshOptions);''',
        1,
    )
    assert 'window.__fixtureChooserOpen = false' in html
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, html)
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)
        control, question = _referral_control_and_question(adapter)
        result = adapter._workday_fill_control(
            control=control, question=question, value="Indeed"
        )
        assert result["status"] == "FILLED", (
            result,
            getattr(adapter, "_workday_option_diagnostic", None),
            getattr(adapter, "_workday_chooser_diagnostic", None),
            page.evaluate("window.__fixtureChooserOpen"),
            page.locator("#referral-options").is_visible(),
            page.locator("#source--source").input_value(),
        )
        assert result["verification"] == "POST_ACTION_PROVIDER_VERIFIED"
        assert page.evaluate("window.__fixtureChooserOpen") is True
        assert page.locator('[data-automation-id="selectedItem-referral"]').inner_text() == "Indeed"
        assert page.evaluate("window.__fixtureSubmitClicked") is False
        browser.close()


def test_crescent_referral_react_portal_with_stale_aria_controls():
    """A stale popup link must not hide one provider-exact option elsewhere."""
    browser_path = resolve_browser_executable()
    plan = _plan()
    html = _fixture_html().replace(
        'id="source--source"',
        'id="source--source" aria-controls="hidden-stale-popup"',
        1,
    ).replace(
        '<div id="referral-selected"></div>',
        '<div id="hidden-stale-popup" hidden></div>'
        '<div id="referral-selected"></div>',
        1,
    )
    assert 'aria-controls="hidden-stale-popup"' in html
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, html)
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")
        adapter = _adapter(page, plan)
        control, question = _referral_control_and_question(adapter)
        result = adapter._workday_fill_control(
            control=control, question=question, value="Indeed"
        )
        assert result["status"] == "FILLED", result
        assert result["verification"] == "POST_ACTION_PROVIDER_VERIFIED"
        assert page.locator('[data-automation-id="selectedItem-referral"]').inner_text() == "Indeed"
        assert page.evaluate("window.__fixtureSubmitClicked") is False
        browser.close()
