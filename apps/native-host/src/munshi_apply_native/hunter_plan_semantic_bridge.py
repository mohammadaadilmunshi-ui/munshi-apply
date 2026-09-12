"""Compatibility bridge between Apply semantic classifications and Hunter plan keys.

MUNSHI Hunter owns candidate truth, canonical application answers, and the
immutable Application Plan. MUNSHI Apply owns browser discovery/classification,
interaction and verification. This module joins those authorities without
allowing browser semantics to invent or downgrade candidate facts.

Only deterministic, singular normal-domain controls are eligible for semantic
alias matching. Repeated employment/education groups continue to require an
exact control/name/text match until the plan carries an explicit repeat binding.
Protected/self-identification/security domains are intentionally never promoted
through this bridge.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

BRIDGE_VERSION = "hunter-plan-semantic-bridge-v1"

# One Apply semantic classification can correspond to more than one historical
# Hunter key while the product migrates toward a single canonical vocabulary.
# Values here are semantic identifiers only; candidate values never live here.
SAFE_SEMANTIC_KEYS: dict[str, frozenset[str]] = {
    "PERSONAL": frozenset({"contact.full_name"}),
    "FIRST_NAME": frozenset({"contact.first_name"}),
    "MIDDLE_NAME": frozenset({"contact.middle_name"}),
    "LAST_NAME": frozenset({"contact.last_name"}),
    "EMAIL": frozenset({"contact.email"}),
    "PHONE": frozenset({"contact.phone"}),
    "LINKEDIN": frozenset({"contact.linkedin"}),
    "PORTFOLIO": frozenset({"contact.portfolio"}),
    "WEBSITE": frozenset({"contact.portfolio"}),
    "CURRENT_LOCATION": frozenset({"contact.location"}),
    "CITY": frozenset({"contact.city"}),
    "STATE_PROVINCE": frozenset({"contact.region"}),
    "POSTAL_CODE": frozenset({"contact.postal_code"}),
    "COUNTRY": frozenset({"contact.country"}),
    "EMPLOYER_NAME": frozenset({"employment.current_employer"}),
    "JOB_TITLE": frozenset({"employment.current_title"}),
    "SCHOOL_NAME": frozenset({"education.institution"}),
    "DEGREE": frozenset({"education.degree", "education.highest_degree"}),
    "FIELD_OF_STUDY": frozenset({"education.field"}),
    "GRADUATION_DATE": frozenset({"education.graduation"}),
    "GPA": frozenset({"education.gpa"}),
    "SALARY_EXPECTATION": frozenset({"compensation.salary"}),
    "START_DATE": frozenset({"availability.start_date"}),
    "NOTICE_PERIOD": frozenset({"availability.notice_period"}),
    "RELOCATION": frozenset({"work.relocation"}),
    "TRAVEL": frozenset({"work.travel"}),
    "REMOTE": frozenset({"work.remote"}),
    "HYBRID": frozenset({"work.hybrid"}),
    "ONSITE": frozenset({"work.onsite"}),
    "PREVIOUS_EMPLOYEE": frozenset({"background.prior_employee"}),
    "WHY_COMPANY": frozenset({"motivation.why_company"}),
    "WHY_ROLE": frozenset({"motivation.why_role"}),
}

# These semantics may be classified accurately by Apply, but their value may only
# come from Hunter's protected/self-ID/post-offer policy. Never use semantic alias
# matching to turn one of them into a normal plaintext fill.
PROTECTED_SEMANTIC_TYPES = frozenset(
    {
        "WORK_AUTHORIZATION_CURRENT",
        "SPONSORSHIP_CURRENT",
        "SPONSORSHIP_FUTURE",
        "IMMIGRATION_ASSISTANCE",
        "SECURITY_CLEARANCE",
        "VETERAN_STATUS",
        "PROTECTED_VETERAN_STATUS",
        "DISABILITY_STATUS",
        "GENDER",
        "RACE_ETHNICITY",
        "EEO_SELF_ID",
        "CONFLICT_OF_INTEREST",
        "NON_COMPETE",
        "BACKGROUND_CHECK",
        "DRUG_SCREENING",
    }
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def semantic_keys(semantic_type: Any) -> frozenset[str]:
    """Return safe Hunter aliases for one Apply semantic type."""
    semantic = str(semantic_type or "").strip().upper()
    if not semantic or semantic in PROTECTED_SEMANTIC_TYPES:
        return frozenset()
    return SAFE_SEMANTIC_KEYS.get(semantic, frozenset())


def _has_repeat_binding(question: Mapping[str, Any], control: Mapping[str, Any]) -> bool:
    return any(
        value is not None
        for value in (
            question.get("repeatGroupId"),
            question.get("repeatIndex"),
            control.get("repeatGroupId"),
            control.get("repeatIndex"),
        )
    )


def answer_matches_question(
    answer: Mapping[str, Any],
    question: Mapping[str, Any],
    control: Mapping[str, Any],
) -> bool:
    """Match a Hunter answer to an observed Apply control deterministically.

    Existing exact matching remains first-class for backwards compatibility.
    Semantic matching is a fallback and is disabled for repeated groups to avoid
    cross-filling one employment/education row into another.
    """
    answer_key = str(answer.get("question_key") or "").strip()
    control_name = str(control.get("name") or "").strip()
    if answer_key and control_name and answer_key == control_name:
        return True

    normalized_question = _normalized(answer.get("normalized_question"))
    raw_text = _normalized(question.get("rawText"))
    if normalized_question and raw_text and normalized_question == raw_text:
        return True

    if _has_repeat_binding(question, control):
        return False

    semantic = str(question.get("semanticType") or "").strip().upper()
    if semantic in PROTECTED_SEMANTIC_TYPES:
        return False
    return bool(answer_key and answer_key in semantic_keys(semantic))


def bridge_status() -> dict[str, Any]:
    """Non-secret diagnostics for CI/health surfaces."""
    return {
        "version": BRIDGE_VERSION,
        "safe_semantic_type_count": len(SAFE_SEMANTIC_KEYS),
        "protected_semantic_type_count": len(PROTECTED_SEMANTIC_TYPES),
        "candidate_value_authority": "hunter_application_plan",
        "browser_semantic_authority": "munshi_apply_semantic_engine",
    }
