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
from munshi_apply_native.hunter_plan_semantic_bridge import (  # noqa: E402
    logical_field_fingerprint,
)
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")

WORKDAY_URL = (
    "https://fixture.wd5.myworkdayjobs.com/en-US/fixture/job/Test/"
    "Fixture_Job/apply"
)
RESUME_BYTES = (
    b"%PDF-1.4\n% MUNSHI Workday universal fixture\n"
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
        "application_id": "application-workday-fixture",
        "plan_id": "application-plan-workday-fixture",
        "plan_digest": "c" * 64,
        "job": {
            "id": "fixture-job-001",
            "company": "Synthetic Employer",
            "title": "People Analytics Specialist",
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
        "answers": [],
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
            "protected_fact_execution": True,
            "self_id_execution": True,
        },
        "submission_authority": False,
    }


NORMAL_VALUES = {
    "referral": "Indeed",
    "previous_employee": "No",
    "country": "United States of America",
    "honorific": "Ms.",
    "first_name": "Ada",
    "middle_name": "Mary",
    "last_name": "Lovelace",
    "street_address": "12 Example Street",
    "city": "Exampletown",
    "state": "New York",
    "postal_code": "12345",
    "phone_device_type": "Mobile",
    "phone_country_code": "United States of America (+1)",
    "phone": "(212) 555-0199",
    "employment_0_title": "People Analytics Intern",
    "employment_0_employer": "Example Motors",
    "employment_0_start": "07/2024",
    "employment_0_end": "01/2025",
    "employment_0_description": "Supported recruiting analytics and HR operations.",
    "employment_1_title": "HR Operations Intern",
    "employment_1_employer": "Example Services",
    "employment_1_start": "11/2023",
    "employment_1_end": "07/2024",
    "employment_1_description": "Maintained HR records and reporting workflows.",
    "education_0_school": "Example University",
    "education_0_degree": "Bachelors Degree",
    "education_1_school": "Example State University",
    "education_1_degree": "Masters Degree",
    "website_0": "https://portfolio.example.test/",
    "salary_expectation": "Open to market-competitive compensation.",
    "language": "English",
    "self_id_name": "Ada Mary Lovelace",
    "self_id_date": "2026-09-27",
}

PROTECTED_BY_SEMANTIC = {
    "WORK_LOCATION_ELIGIBILITY": "Yes",
    "AGE_18_PLUS": "Yes",
    "SPONSORSHIP_FUTURE": "Yes",
    "GENDER": "I do not want to answer",
    "RACE_ETHNICITY": "I do not want to answer",
    "HISPANIC_LATINO": "I do not want to answer",
    "VETERAN_STATUS": "I do not want to answer",
    "DISABILITY_STATUS": "I do not want to answer",
}


def _route(page, html: str) -> None:
    def handler(route):
        if route.request.url == WORKDAY_URL and route.request.method == "GET":
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        route.abort()

    page.route("**/*", handler)


def _bind_protected_answers(adapter: PlanBrowserAdapter, page, plan: dict):
    protected_values: dict[str, str] = {}
    seen_semantics: set[str] = set()
    for page_index in (2, 3, 4):
        page.evaluate("index => window.fixtureShowPage(index)", page_index)
        described = adapter._scan()
        controls = {
            str(item["controlId"]): item
            for item in described["page"]["controls"]
        }
        for question in described["page"]["questions"]:
            semantic = str(question.get("semanticType") or "").upper()
            if semantic not in PROTECTED_BY_SEMANTIC or semantic in seen_semantics:
                continue
            control = controls.get(str(question.get("controlId") or ""))
            if not control:
                continue
            fingerprint = logical_field_fingerprint(question, control)
            if not fingerprint:
                continue
            sensitivity = str(
                question.get("sensitivityClass")
                or ("SELF_ID" if semantic in {
                    "GENDER",
                    "RACE_ETHNICITY",
                    "HISPANIC_LATINO",
                    "VETERAN_STATUS",
                    "DISABILITY_STATUS",
                } else "PROTECTED")
            ).upper()
            key = f"fixture.protected.{semantic.casefold()}"
            plan["answers"].append(
                {
                    "question_key": key,
                    "normalized_question": str(question.get("rawText") or ""),
                    "sensitivity_class": sensitivity,
                    "autofill_allowed": True,
                    "execution_value": None,
                    "secure_resolver_ref": (
                        "hunter-secure://candidate-truth/"
                        + key.replace(".", "/")
                    ),
                    "universal_binding_fingerprint": fingerprint,
                }
            )
            protected_values[key] = PROTECTED_BY_SEMANTIC[semantic]
            seen_semantics.add(semantic)
    page.evaluate("() => window.fixtureShowPage(0)")
    assert set(PROTECTED_BY_SEMANTIC) <= seen_semantics
    return protected_values


def _bind_normal_plan_answers(adapter: PlanBrowserAdapter, page, plan: dict) -> set[str]:
    """Create immutable, scanner-bound approved answers without browser value overrides.

    The original six-page acceptance case injects resolved_values directly.
    This lane covers the separate production dependency: actual plan answers
    matching Workday controls, including repeated education/employment groups.
    """
    bound: set[str] = set()
    for page_index in range(5):
        page.evaluate("index => window.fixtureShowPage(index)", page_index)
        described = adapter._scan()
        controls = {
            str(item["controlId"]): item
            for item in described["page"]["controls"]
        }
        for question in described["page"]["questions"]:
            control = controls.get(str(question.get("controlId") or ""))
            if not control:
                continue
            name = str(control.get("name") or "")
            if name not in NORMAL_VALUES or name in bound:
                continue
            fingerprint = logical_field_fingerprint(question, control)
            assert fingerprint, f"No logical-field identity for {name}"
            plan["answers"].append({
                "question_key": "runtime-question:" + str(control["controlId"]),
                "normalized_question": "",
                "sensitivity_class": "NORMAL",
                "autofill_allowed": True,
                "execution_value": NORMAL_VALUES[name],
                "universal_binding_fingerprint": fingerprint,
            })
            bound.add(name)
    page.evaluate("() => window.fixtureShowPage(0)")
    return bound


@pytest.mark.parametrize(
    "normal_answer_mode",
    ["resolved_values", "immutable_plan"],
)
def test_workday_six_page_fixture_prepares_to_reconciled_review_without_submit(normal_answer_mode: str):
    browser_path = resolve_browser_executable()
    fixture = (
        _root()
        / "apps/native-host/tests/browser/fixtures/workday_universal_six_page.html"
    )
    html = fixture.read_text(encoding="utf-8")
    plan = _plan()

    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=browser_path)
        page = browser.new_page()
        _route(page, html)
        page.goto(WORKDAY_URL, wait_until="domcontentloaded")

        protected_values: dict[str, str] = {}

        def protected_resolver(current, answer):
            assert current is plan
            key = str(answer["question_key"])
            return {
                "question_key": key,
                "sensitivity": str(answer["sensitivity_class"]),
                "provenance": "candidate_truth_protected_domain",
                "value": protected_values[key],
            }

        legal_proofs: list[dict] = []

        def legal_authorizer(current, identity):
            assert current is plan
            proof = {
                "authorized": True,
                "submission_authority": False,
                "attestation_identity": dict(identity),
                "authorization_digest": "d" * 64,
            }
            legal_proofs.append(proof)
            return proof

        runtime = _root() / "apps/native-host/browser-dist/plan-runtime.js"
        assert runtime.is_file(), "run npm run build before the real-browser lane"
        adapter = PlanBrowserAdapter(
            page,
            artifact_reader=lambda current: RESUME_BYTES,
            current_plan=lambda current: current is plan,
            runtime_path=runtime,
            protected_value_resolver=protected_resolver,
            legal_attestation_authorizer=legal_authorizer,
        )
        protected_values.update(_bind_protected_answers(adapter, page, plan))
        if normal_answer_mode == "immutable_plan":
            bound = _bind_normal_plan_answers(adapter, page, plan)
            assert {"phone", "referral", "employment_0_title", "education_0_school"} <= bound
            supplied = {}
        else:
            supplied = NORMAL_VALUES

        prepared = adapter.prepare_form(
            plan=plan,
            checkpoint=None,
            resolved_values=supplied,
        )

        assert page.locator("body").get_attribute("data-page") == "5"
        assert page.locator("body").get_attribute("data-submitted") is None
        assert prepared["resume_uploaded"] is True
        assert prepared["resume_sha256"] == RESUME_SHA
        assert prepared["unresolved"] == []
        assert prepared["validation_errors"] == []
        assert prepared["prepared_page_count"] >= 6
        assert prepared["review_reconciliation"]["status"] == "MATCH"
        assert prepared["review_reconciliation"]["mismatches"] == []
        assert len(prepared["review_reconciliation"]["snapshot_digest"]) == 64

        assert page.locator('[name="phone_extension"]').input_value() == ""
        assert page.locator('[name="employment_0_location"]').input_value() == ""
        assert page.locator('[name="education_0_field"]').input_value() == ""
        assert page.locator('[name="employee_id"]').input_value() == ""

        assert page.locator('[name="employment_0_title"]').input_value() == (
            "People Analytics Intern"
        )
        assert page.locator('[name="employment_1_title"]').input_value() == (
            "HR Operations Intern"
        )
        assert page.locator('[name="education_0_school"]').input_value() == (
            "Example University"
        )
        assert page.locator('[name="education_1_school"]').input_value() == (
            "Example State University"
        )

        assert page.locator('[name="legal_attestation"]').is_checked()
        assert len(legal_proofs) == 1
        assert legal_proofs[0]["attestation_identity"]["semantic_type"] == (
            "LEGAL_ATTESTATION"
        )
        assert len(
            legal_proofs[0]["attestation_identity"]["terms_identity_digest"]
        ) == 64

        checked_disability = page.locator(
            '[name="disability_status"]:checked'
        )
        assert checked_disability.count() == 1
        assert checked_disability.first.get_attribute("value") == (
            "I do not want to answer"
        )

        described = page.evaluate("MunshiPlanRuntime.describeForm()")
        final_submit = [
            item
            for item in described["page"]["navigationCandidates"]
            if item["action"] == "FINAL_SUBMIT"
        ]
        assert len(final_submit) == 1
        browser.close()
