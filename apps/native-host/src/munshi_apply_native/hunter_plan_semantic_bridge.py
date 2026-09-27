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

import hashlib
import json
import re
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
    "PHONE_DEVICE_TYPE": frozenset({"application.phone_device_type"}),
    "PHONE_COUNTRY_CODE": frozenset({"contact.phone_country_code"}),
    "PHONE_EXTENSION": frozenset({"contact.phone_extension"}),
    "SELF_ID_NAME": frozenset({"contact.full_name"}),
    "ADDRESS": frozenset({"contact.address_line1"}),
    "STREET_ADDRESS": frozenset({"contact.address_line1"}),
    "ADDRESS_LINE_2": frozenset({"contact.address_line2"}),
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
        "WORK_LOCATION_ELIGIBILITY",
        "AGE_18_PLUS",
        "SPONSORSHIP_CURRENT",
        "SPONSORSHIP_FUTURE",
        "IMMIGRATION_ASSISTANCE",
        "SECURITY_CLEARANCE",
        "VETERAN_STATUS",
        "PROTECTED_VETERAN_STATUS",
        "DISABILITY_STATUS",
        "GENDER",
        "RACE_ETHNICITY",
        "HISPANIC_LATINO",
        "EEO_SELF_ID",
        "EMPLOYEE_ID",
        "LEGAL_ATTESTATION",
        "CONFLICT_OF_INTEREST",
        "NON_COMPETE",
        "BACKGROUND_CHECK",
        "DRUG_SCREENING",
    }
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _fingerprint_norm(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^a-z0-9+/#. _-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sha_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _option_texts(question: Mapping[str, Any], control: Mapping[str, Any]) -> list[str]:
    raw = question.get("options")
    if not isinstance(raw, list):
        raw = control.get("options")
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw[:250]:
        if isinstance(item, Mapping):
            value = item.get("label") or item.get("text") or item.get("value")
        else:
            value = item
        normalized = _fingerprint_norm(value)
        if normalized:
            values.append(normalized)
    return values


def logical_field_fingerprint(
    question: Mapping[str, Any],
    control: Mapping[str, Any],
) -> str | None:
    """Mirror Hunter's provider-neutral logical-field fingerprint.

    Prefer the scanner's canonical logicalFieldFingerprintInputs object. This
    prevents Hunter/Apply reconstruction drift when a browser control has an
    empty observed inputType but the DOM element has a more specific native type.
    """
    raw_inputs = question.get("logicalFieldFingerprintInputs")
    if not isinstance(raw_inputs, Mapping):
        raw_inputs = question.get("logical_field_fingerprint_inputs")
    scanner_inputs = dict(raw_inputs) if isinstance(raw_inputs, Mapping) else {}

    def scanner_or(key: str, fallback: Any) -> Any:
        return scanner_inputs[key] if key in scanner_inputs else fallback

    repeat_group = scanner_or(
        "repeatGroupId",
        question.get("repeatGroupId")
        if question.get("repeatGroupId") is not None
        else control.get("repeatGroupId"),
    )
    repeat_index = scanner_or(
        "repeatIndex",
        question.get("repeatIndex")
        if question.get("repeatIndex") is not None
        else control.get("repeatIndex"),
    )
    if repeat_group is not None and repeat_index is None:
        return None
    try:
        repeat_index_value = int(repeat_index) if repeat_index is not None else None
    except (TypeError, ValueError):
        return None

    question_identity = {
        "raw_question": _fingerprint_norm(question.get("rawText") or question.get("question")),
        "label": _fingerprint_norm(
            scanner_or("label", question.get("label") or control.get("label"))
        ),
        "placeholder": _fingerprint_norm(
            question.get("placeholder") or control.get("placeholder")
        ),
        "name": _fingerprint_norm(
            scanner_or(
                "fieldName",
                question.get("fieldName") or question.get("name") or control.get("name"),
            )
        ),
    }
    previous = question.get("previousLabels") or []
    next_values = question.get("nextLabels") or []
    section_identity = {
        "section": _fingerprint_norm(
            scanner_or("sectionHeading", question.get("sectionHeading"))
        ),
        "previous": [_fingerprint_norm(item) for item in previous if _fingerprint_norm(item)],
        "next": [_fingerprint_norm(item) for item in next_values if _fingerprint_norm(item)],
    }
    scanner_option_signature = _fingerprint_norm(scanner_inputs.get("optionSignature"))
    options = (
        _sha_json({"scanner_option_signature": scanner_option_signature})
        if scanner_option_signature
        else _sha_json(_option_texts(question, control))
    )
    logical = {
        "question": question_identity,
        "section": section_identity,
        "input_type": _fingerprint_norm(
            scanner_or(
                "inputType",
                question.get("inputType")
                if question.get("inputType") is not None
                else control.get("inputType"),
            )
        ),
        "role": _fingerprint_norm(
            scanner_or("role", question.get("role") or control.get("role"))
        ),
        "autocomplete": _fingerprint_norm(
            scanner_or(
                "autocomplete",
                question.get("autocomplete")
                if question.get("autocomplete") is not None
                else control.get("autocomplete"),
            )
        ),
        "option_signature": options,
        "repeat_group": _fingerprint_norm(repeat_group),
        "repeat_index": repeat_index_value,
    }
    return _sha_json(logical)


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
    semantic = str(question.get("semanticType") or "").strip().upper()
    answer_sensitivity = str(answer.get("sensitivity_class") or "NORMAL").upper()

    # Protected, self-identification, post-offer, and mandate-scoped policy
    # concepts never enter the normal semantic/exact-match lane. This check must
    # precede legacy exact provider-key matching so a coincidental field name
    # cannot downgrade the stricter Hunter authority path.
    if semantic in PROTECTED_SEMANTIC_TYPES or answer_sensitivity != "NORMAL":
        return False

    answer_key = str(answer.get("question_key") or "").strip()
    control_name = str(control.get("name") or "").strip()
    if answer_key and control_name and answer_key == control_name:
        return True

    # Stable scanner identity for controlled inputs without a name.
    question_id = str(question.get("questionId") or "").strip()
    if answer_key and question_id and answer_key == question_id:
        return True

    normalized_question = _normalized(answer.get("normalized_question"))
    raw_text = _normalized(question.get("rawText"))
    if normalized_question and raw_text and normalized_question == raw_text:
        return True

    binding = str(answer.get("universal_binding_fingerprint") or "").strip().lower()
    if binding:
        if str(answer.get("sensitivity_class") or "NORMAL").upper() != "NORMAL":
            return False
        observed_binding = logical_field_fingerprint(question, control)
        if observed_binding and observed_binding == binding:
            return True

    if _has_repeat_binding(question, control):
        return False

    return bool(answer_key and answer_key in semantic_keys(semantic))


def protected_answer_matches_question(
    answer: Mapping[str, Any],
    question: Mapping[str, Any],
    control: Mapping[str, Any],
) -> bool:
    """Bind one protected/self-ID plan answer to exactly one browser field.

    Unlike normal answers, protected values never use fuzzy semantics, provider
    wording, or legacy answer-key aliases. The immutable Hunter plan must carry
    the value-free logical-field fingerprint created from the same structural
    browser observation, and the current field must reproduce it exactly.
    """
    sensitivity = str(answer.get("sensitivity_class") or "").strip().upper()
    if sensitivity not in {"PROTECTED", "SELF_ID"}:
        return False
    if answer.get("autofill_allowed") is not True:
        return False
    if answer.get("execution_value") is not None:
        return False
    reference = str(answer.get("secure_resolver_ref") or "").strip()
    if not reference.startswith("hunter-secure://candidate-truth/"):
        return False

    expected = str(answer.get("universal_binding_fingerprint") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return False
    observed = logical_field_fingerprint(question, control)
    if observed is None or observed != expected:
        return False

    semantic = str(question.get("semanticType") or "").strip().upper()
    if semantic not in PROTECTED_SEMANTIC_TYPES:
        return False
    return True


def bridge_status() -> dict[str, Any]:
    """Non-secret diagnostics for CI/health surfaces."""
    return {
        "version": BRIDGE_VERSION,
        "safe_semantic_type_count": len(SAFE_SEMANTIC_KEYS),
        "protected_semantic_type_count": len(PROTECTED_SEMANTIC_TYPES),
        "candidate_value_authority": "hunter_application_plan",
        "browser_semantic_authority": "munshi_apply_semantic_engine",
        "universal_binding_authority": "hunter_application_plan",
    }
