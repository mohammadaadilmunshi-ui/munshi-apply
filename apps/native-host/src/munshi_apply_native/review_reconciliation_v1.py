"""Provider-neutral final-review reconciliation helpers.

This module never promotes provider-rendered text into Candidate Truth. Raw review
text is transient input only; callers persist the digest and safe mismatch codes.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm(value: Any) -> str:
    return _compact(value).casefold()


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normal_fields(fields: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in fields:
        item = dict(raw)
        if str(item.get("sensitivity_class") or "NORMAL").upper() != "NORMAL":
            continue
        value = _compact(item.get("display_value"))
        if not value or value == "[protected value]":
            continue
        result.append(item)
    return result


def _by_semantic(fields: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in fields:
        grouped[str(item.get("semantic_type") or "").upper()].append(dict(item))
    return dict(grouped)


def _one_value(grouped: Mapping[str, list[dict[str, Any]]], semantic: str) -> str:
    values = {
        _compact(item.get("display_value"))
        for item in grouped.get(semantic, [])
        if _compact(item.get("display_value"))
        and _compact(item.get("display_value")) != "[protected value]"
    }
    return next(iter(values)) if len(values) == 1 else ""


def _review_line_after(lines: list[str], label: str) -> str:
    wanted = _norm(label)
    for index, line in enumerate(lines):
        if _norm(line).rstrip(":") != wanted.rstrip(":"):
            continue
        for candidate in lines[index + 1 : index + 5]:
            value = _compact(candidate)
            if value:
                return value
    return ""


def reconcile_provider_review(
    *,
    review_text: str,
    prepared_fields: Iterable[Mapping[str, Any]],
    expected_resume_sha256: str,
    observed_resume_sha256: str,
    final_submission_boundary: bool,
) -> dict[str, Any]:
    """Reconcile a provider Review rendering against already-prepared evidence.

    The function intentionally uses only deterministic negative invariants. It
    does not infer missing candidate facts and never returns raw review text.
    """
    all_fields = [dict(item) for item in prepared_fields]
    compact_review = _compact(review_text)
    normalized_review = _norm(review_text)
    lines = [_compact(line) for line in str(review_text or "").splitlines() if _compact(line)]
    fields = _normal_fields(all_fields)
    grouped = _by_semantic(fields)
    mismatches: list[dict[str, Any]] = []

    def add(code: str, detail: str, semantic: str | None = None) -> None:
        item: dict[str, Any] = {"code": code, "safe_detail": detail[:1000]}
        if semantic:
            item["semantic_type"] = semantic
        if item not in mismatches:
            mismatches.append(item)

    if not final_submission_boundary:
        return {
            "status": "INCOMPLETE",
            "snapshot_digest": _sha(compact_review),
            "mismatches": [
                {
                    "code": "MISSING_REQUIRED",
                    "safe_detail": (
                        "Final provider review/submit boundary was not uniquely observed."
                    ),
                }
            ],
        }

    expected_resume = str(expected_resume_sha256 or "").strip().lower()
    observed_resume = str(observed_resume_sha256 or "").strip().lower()
    if (
        len(expected_resume) != 64
        or len(observed_resume) != 64
        or expected_resume != observed_resume
    ):
        add("RESUME_SHA_MISMATCH", "Browser resume digest differs from the approved artifact.")

    first = _one_value(grouped, "FIRST_NAME")
    middle = _one_value(grouped, "MIDDLE_NAME")
    last = _one_value(grouped, "LAST_NAME")
    if first and last:
        first_tokens = _norm(first).split()
        middle_tokens = _norm(middle).split() if middle else []
        last_tokens = _norm(last).split()
        if (
            middle_tokens
            and (
                all(token in first_tokens for token in middle_tokens)
                or all(token in last_tokens for token in middle_tokens)
            )
        ):
            add(
                "NAME_RECOMPOSITION",
                "Structured legal-name parts overlap before final Review.",
                "MIDDLE_NAME",
            )
        expected_name = _norm(" ".join(value for value in (first, middle, last) if value))
        if expected_name and expected_name not in normalized_review:
            add(
                "NAME_RECOMPOSITION",
                "Final Review does not contain the canonical structured legal-name sequence.",
                "FIRST_NAME",
            )

    phone = _one_value(grouped, "PHONE")
    extension = _one_value(grouped, "PHONE_EXTENSION")
    phone_line = _review_line_after(lines, "Phone")
    if phone:
        expected_phone_digits = _digits(phone)
        rendered_phone_digits = _digits(phone_line)
        if expected_phone_digits:
            local = expected_phone_digits[-10:]
            if local and local not in rendered_phone_digits:
                add(
                    "PHONE_MISMATCH",
                    "Final Review phone digits differ from the prepared canonical phone.",
                    "PHONE",
                )
    if not extension and phone_line:
        if re.search(r"(?:\bext(?:ension)?\.?|\bx)\s*[:#.-]?\s*\d{3,}\b", phone_line, re.I):
            add(
                "PHONE_EXTENSION_WITHOUT_FACT",
                "Final Review renders a phone extension although no extension fact was prepared.",
                "PHONE_EXTENSION",
            )

    for semantic, label in (
        ("STREET_ADDRESS", "street address"),
        ("CITY", "city"),
        ("POSTAL_CODE", "postal code"),
    ):
        value = _one_value(grouped, semantic)
        if value and _norm(value) not in normalized_review:
            add(
                "ADDRESS_MISMATCH",
                f"Final Review is missing the prepared {label}.",
                semantic,
            )

    # Repeated rows use high-signal row identity values. Repeated employer names
    # alone are intentionally insufficient because one candidate may hold more
    # than one role at the same company.
    for semantic in ("JOB_TITLE", "SCHOOL_NAME"):
        for item in grouped.get(semantic, []):
            observation = dict(item.get("question_observation") or {})
            repeat_group = (
                item.get("repeat_group_id")
                if item.get("repeat_group_id") is not None
                else observation.get("repeat_group")
            )
            repeat_index = (
                item.get("repeat_index")
                if item.get("repeat_index") is not None
                else observation.get("repeat_index")
            )
            if repeat_group is None and repeat_index is None:
                continue
            value = _compact(item.get("display_value"))
            if value and _norm(value) not in normalized_review:
                mismatch = {
                    "code": "REPEAT_GROUP_MISMATCH",
                    "semantic_type": semantic,
                    "repeat_group_id": repeat_group,
                    "repeat_index": repeat_index,
                    "safe_detail": "Final Review is missing a row-bound prepared value.",
                }
                if mismatch not in mismatches:
                    mismatches.append(mismatch)

    snapshot_material = "\n".join(
        [
            _sha(compact_review),
            expected_resume,
            observed_resume,
            *sorted(
                f"{str(item.get('semantic_type') or '')}:{str(item.get('value_digest') or '')}:"
                f"{str(item.get('repeat_group_id') or '')}:{str(item.get('repeat_index') or '')}"
                for item in all_fields
            ),
        ]
    )
    return {
        "status": "MATCH" if not mismatches else "MISMATCH",
        "snapshot_digest": _sha(snapshot_material),
        "mismatches": mismatches,
    }
