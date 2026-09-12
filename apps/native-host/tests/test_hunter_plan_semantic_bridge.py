from __future__ import annotations

from pathlib import Path

from munshi_apply_native.hunter_plan_semantic_bridge import (
    PROTECTED_SEMANTIC_TYPES,
    answer_matches_question,
    bridge_status,
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
