from __future__ import annotations

from pathlib import Path

from munshi_apply_native.hunter_plan_semantic_bridge import (
    PROTECTED_SEMANTIC_TYPES,
    answer_matches_question,
    bridge_status,
    logical_field_fingerprint,
    semantic_keys,
)


def _answer(key: str, question: str = "") -> dict[str, object]:
    return {
        "question_key": key,
        "normalized_question": question,
        "sensitivity_class": "NORMAL",
        "execution_value": "example",
        "autofill_allowed": True,
    }


def _question(
    semantic_type: str,
    raw_text: str = "",
    *,
    repeat_group_id: str | None = None,
    repeat_index: int | None = None,
) -> dict[str, object]:
    return {
        "semanticType": semantic_type,
        "rawText": raw_text,
        "repeatGroupId": repeat_group_id,
        "repeatIndex": repeat_index,
    }


def _control(
    name: str = "",
    *,
    repeat_group_id: str | None = None,
    repeat_index: int | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "repeatGroupId": repeat_group_id,
        "repeatIndex": repeat_index,
    }


def test_apply_first_name_semantics_match_hunter_canonical_key() -> None:
    assert answer_matches_question(
        _answer("contact.first_name"),
        _question("FIRST_NAME", "Given name"),
        _control("candidateGivenName"),
    ) is True


def test_apply_last_name_variants_match_same_hunter_key() -> None:
    answer = _answer("contact.last_name")
    assert answer_matches_question(
        answer,
        _question("LAST_NAME", "Surname"),
        _control("surnameField"),
    ) is True
    assert answer_matches_question(
        answer,
        _question("LAST_NAME", "Family name"),
        _control("familyNameField"),
    ) is True


def test_existing_exact_control_name_match_is_preserved() -> None:
    assert answer_matches_question(
        _answer("custom.provider.field"),
        _question("UNKNOWN", "Some provider wording"),
        _control("custom.provider.field"),
    ) is True


def test_existing_exact_question_text_match_is_preserved() -> None:
    assert answer_matches_question(
        _answer("unknown.key", "Why this exact wording?"),
        _question("UNKNOWN", "  why THIS exact wording? "),
        _control("providerGeneratedName"),
    ) is True


def test_semantic_alias_does_not_cross_fill_repeated_groups() -> None:
    assert answer_matches_question(
        _answer("employment.current_employer"),
        _question(
            "EMPLOYER_NAME",
            "Employer",
            repeat_group_id="employment",
            repeat_index=1,
        ),
        _control(
            "employer_1",
            repeat_group_id="employment",
            repeat_index=1,
        ),
    ) is False


def test_protected_semantics_never_become_normal_aliases() -> None:
    for semantic_type in PROTECTED_SEMANTIC_TYPES:
        assert semantic_keys(semantic_type) == frozenset()
    assert answer_matches_question(
        _answer("eligibility.work_authorized_us"),
        _question("WORK_AUTHORIZATION_CURRENT", "Authorized to work?"),
        _control("workAuth"),
    ) is False


def test_bridge_diagnostics_preserve_authority_boundary() -> None:
    status = bridge_status()
    assert status["candidate_value_authority"] == "hunter_application_plan"
    assert status["browser_semantic_authority"] == "munshi_apply_semantic_engine"
    assert status["safe_semantic_type_count"] > 20


def test_plan_browser_adapter_is_wired_to_semantic_bridge() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "munshi_apply_native"
        / "plan_browser_adapter.py"
    ).read_text(encoding="utf-8")
    assert "from .hunter_plan_semantic_bridge import answer_matches_question" in source
    assert "and answer_matches_question(a, question, control)" in source


def _rich_question(
    *,
    semantic_type: str = "STATE_PROVINCE",
    raw_text: str = "State / Province",
    label: str = "State",
    repeat_group_id: str | None = None,
    repeat_index: int | None = None,
) -> dict[str, object]:
    return {
        "semanticType": semantic_type,
        "rawText": raw_text,
        "label": label,
        "placeholder": "Select state",
        "fieldName": "candidate_region",
        "sectionHeading": "Contact Information",
        "previousLabels": ["City"],
        "nextLabels": ["Postal code"],
        "inputType": "select-one",
        "role": "combobox",
        "autocomplete": "address-level1",
        "options": ["New Jersey", "New York", "Pennsylvania"],
        "repeatGroupId": repeat_group_id,
        "repeatIndex": repeat_index,
    }


def _rich_control(
    *,
    control_id: str = "ctl-state-v1",
    repeat_group_id: str | None = None,
    repeat_index: int | None = None,
) -> dict[str, object]:
    return {
        "controlId": control_id,
        "name": "candidate_region",
        "label": "State",
        "placeholder": "Select state",
        "inputType": "select-one",
        "role": "combobox",
        "autocomplete": "address-level1",
        "options": ["New Jersey", "New York", "Pennsylvania"],
        "repeatGroupId": repeat_group_id,
        "repeatIndex": repeat_index,
    }


def test_universal_binding_matches_after_control_id_and_semantic_change() -> None:
    original_question = _rich_question(semantic_type="STATE_PROVINCE")
    original_control = _rich_control(control_id="ctl-state-v1")
    fingerprint = logical_field_fingerprint(original_question, original_control)
    assert fingerprint is not None and len(fingerprint) == 64

    answer = {
        **_answer("unknown.runtime.region"),
        "universal_concept_id": "contact.region",
        "universal_binding_fingerprint": fingerprint,
    }
    rerendered_question = _rich_question(semantic_type="UNKNOWN")
    rerendered_control = _rich_control(control_id="ctl-state-v2")
    assert answer_matches_question(answer, rerendered_question, rerendered_control) is True


def test_universal_binding_does_not_cross_repeated_rows() -> None:
    row_one_question = _rich_question(
        semantic_type="UNKNOWN",
        raw_text="Employer",
        label="Employer",
        repeat_group_id="employment",
        repeat_index=1,
    )
    row_one_control = {
        **_rich_control(
            control_id="employer-row-1",
            repeat_group_id="employment",
            repeat_index=1,
        ),
        "name": "employer",
        "label": "Employer",
        "placeholder": "",
        "autocomplete": "",
        "options": [],
        "inputType": "text",
        "role": "textbox",
    }
    row_one_question.update(
        {
            "placeholder": "",
            "fieldName": "employer",
            "sectionHeading": "Work Experience",
            "previousLabels": ["Job title"],
            "nextLabels": ["Start date"],
            "inputType": "text",
            "role": "textbox",
            "autocomplete": "",
            "options": [],
        }
    )
    fingerprint = logical_field_fingerprint(row_one_question, row_one_control)
    assert fingerprint is not None
    answer = {
        **_answer("experience.1.employer"),
        "universal_binding_fingerprint": fingerprint,
    }

    row_two_question = dict(row_one_question)
    row_two_question["repeatIndex"] = 2
    row_two_control = dict(row_one_control)
    row_two_control["repeatIndex"] = 2
    row_two_control["controlId"] = "employer-row-2"
    assert answer_matches_question(answer, row_two_question, row_two_control) is False


def test_universal_binding_rejects_unscoped_repeated_control() -> None:
    question = _rich_question(
        semantic_type="UNKNOWN",
        raw_text="Employer",
        label="Employer",
        repeat_group_id="employment",
        repeat_index=None,
    )
    control = _rich_control(
        control_id="employer-unscoped",
        repeat_group_id="employment",
        repeat_index=None,
    )
    assert logical_field_fingerprint(question, control) is None


def test_matching_universal_fingerprint_cannot_bypass_protected_boundary() -> None:
    question = _rich_question(semantic_type="UNKNOWN")
    control = _rich_control()
    fingerprint = logical_field_fingerprint(question, control)
    assert fingerprint is not None
    protected_answer = {
        **_answer("eligibility.work_authorized_us"),
        "sensitivity_class": "PROTECTED",
        "universal_binding_fingerprint": fingerprint,
    }
    assert answer_matches_question(protected_answer, question, control) is False


def test_bridge_reports_universal_binding_authority() -> None:
    status = bridge_status()
    assert status["universal_binding_authority"] == "hunter_application_plan"


def test_segmented_phone_semantics_map_to_distinct_hunter_keys() -> None:
    assert semantic_keys("PHONE") == frozenset({"contact.phone"})
    assert semantic_keys("PHONE_DEVICE_TYPE") == frozenset(
        {"application.phone_device_type"}
    )
    assert semantic_keys("PHONE_COUNTRY_CODE") == frozenset(
        {"contact.phone_country_code"}
    )
    assert semantic_keys("PHONE_EXTENSION") == frozenset(
        {"contact.phone_extension"}
    )
    assert len(
        {
            next(iter(semantic_keys("PHONE"))),
            next(iter(semantic_keys("PHONE_DEVICE_TYPE"))),
            next(iter(semantic_keys("PHONE_COUNTRY_CODE"))),
            next(iter(semantic_keys("PHONE_EXTENSION"))),
        }
    ) == 4


def test_structural_self_id_name_remains_normal_but_policy_fields_do_not() -> None:
    assert semantic_keys("SELF_ID_NAME") == frozenset({"contact.full_name"})
    for semantic in (
        "WORK_LOCATION_ELIGIBILITY",
        "AGE_18_PLUS",
        "HISPANIC_LATINO",
        "EMPLOYEE_ID",
        "SELF_ID_DATE",
        "LEGAL_ATTESTATION",
    ):
        assert semantic_keys(semantic) == frozenset()


def test_protected_semantic_cannot_bypass_boundary_via_exact_provider_key() -> None:
    answer = _answer("provider.exact.key")
    assert answer_matches_question(
        answer,
        _question("AGE_18_PLUS", "Are you at least 18 years of age?"),
        _control("provider.exact.key"),
    ) is False


def test_non_normal_answer_cannot_bypass_boundary_via_exact_question_text() -> None:
    answer = {
        **_answer("provider.answer", "Do you identify as Hispanic or Latino?"),
        "sensitivity_class": "SELF_ID",
    }
    assert answer_matches_question(
        answer,
        _question("UNKNOWN", "Do you identify as Hispanic or Latino?"),
        _control("unrelated-control"),
    ) is False


def test_stable_question_id_matches_when_control_name_is_empty() -> None:
    question = _question("REFERRAL", "Provider text may rerender")
    question["questionId"] = "q-referral-source"
    assert answer_matches_question(
        _answer("q-referral-source", "Older display wording"),
        question,
        _control(""),
    ) is True
