from __future__ import annotations

import re
from typing import Any

MAX_MECHANICS_ACTIONS = 24
ALLOWED_KEYS = {"ArrowDown", "ArrowUp", "Enter", "Tab", "Escape", "Space"}
ALLOWED_WAIT_STATES = {
    "TARGET_VISIBLE",
    "TARGET_HIDDEN",
    "OPTIONS_VISIBLE",
    "VALUE_COMMITTED",
    "FILE_ATTACHED",
    "URL_CHANGED",
    "PAGE_STABLE",
    "AUTH_STATE_CHANGED",
}
REFERENCE_FIELDS = {
    "TYPE_ANSWER_REF": "answerRef",
    "FILL_SECRET_REF": "secretRef",
    "FILL_VERIFICATION_ARTIFACT": "verificationRef",
    "UPLOAD_ARTIFACT": "artifactRef",
    "OPEN_LINK": "verificationRef",
}
TARGET_ACTIONS = {
    "FOCUS",
    "CLICK",
    "NEXT",
    "TYPE_ANSWER_REF",
    "FILL_SECRET_REF",
    "FILL_VERIFICATION_ARTIFACT",
    "UPLOAD_ARTIFACT",
    "SELECT",
    "KEY",
}
LEGACY_ACTIONS = {"FOCUS", "CLICK", "SELECT_EXACT_OPTION", "TYPE", "KEY", "WAIT_FOR_STATE"}
_FORBIDDEN_VALUE_KEYS = {
    "value",
    "text",
    "password",
    "code",
    "otp",
    "url",
    "href",
    "selector",
    "xpath",
    "javascript",
    "script",
}
_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,31}:[A-Za-z0-9_.:@/-]{1,192}$")
_TARGET_RE = re.compile(r"^mt-[a-f0-9]{16,64}$")


class MechanicsActionError(ValueError):
    pass


def _ref(value: object, field: str) -> str:
    if not isinstance(value, str) or not _REF_RE.fullmatch(value.strip()):
        raise MechanicsActionError(f"{field} must be an opaque mechanics reference")
    return value.strip()


def _target(value: object) -> str:
    if not isinstance(value, str) or not _TARGET_RE.fullmatch(value.strip()):
        raise MechanicsActionError("targetRef must reference an observed mechanics target")
    return value.strip()


def _reject_literal_material(raw: dict[str, Any]) -> None:
    for key in raw:
        if str(key).casefold() in _FORBIDDEN_VALUE_KEYS:
            raise MechanicsActionError(
                "Mechanics actions must use opaque refs; literal values/selectors are forbidden"
            )


def validate_mechanics_actions(
    value: object,
    *,
    allowed_target_refs: set[str] | None = None,
    allowed_value_refs: set[str] | None = None,
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > MAX_MECHANICS_ACTIONS:
        raise MechanicsActionError(
            f"Mechanics fallback must return 1-{MAX_MECHANICS_ACTIONS} bounded actions"
        )
    normalized: list[dict[str, object]] = []
    for raw_value in value:
        if not isinstance(raw_value, dict):
            raise MechanicsActionError("Mechanics actions must be objects")
        raw = dict(raw_value)
        _reject_literal_material(raw)
        action_type = str(raw.get("type") or "").strip().upper()

        if action_type in {"FOCUS", "CLICK", "NEXT"}:
            target_ref = _target(raw.get("targetRef"))
            item: dict[str, object] = {"type": action_type, "targetRef": target_ref}
        elif action_type in REFERENCE_FIELDS:
            ref_field = REFERENCE_FIELDS[action_type]
            ref_value = _ref(raw.get(ref_field), ref_field)
            item = {"type": action_type, ref_field: ref_value}
            if action_type != "OPEN_LINK":
                item["targetRef"] = _target(raw.get("targetRef"))
        elif action_type == "SELECT":
            target_ref = _target(raw.get("targetRef"))
            value_ref = _ref(raw.get("valueRef"), "valueRef")
            item = {"type": "SELECT", "targetRef": target_ref, "valueRef": value_ref}
        elif action_type == "KEY":
            target_ref = _target(raw.get("targetRef"))
            key = str(raw.get("key") or "")
            if key not in ALLOWED_KEYS:
                raise MechanicsActionError("Mechanics KEY is not allowed")
            item = {"type": "KEY", "targetRef": target_ref, "key": key}
        elif action_type == "WAIT_FOR_STATE":
            state = str(raw.get("state") or "").strip().upper()
            if state not in ALLOWED_WAIT_STATES:
                raise MechanicsActionError("Mechanics wait state is not allowed")
            item = {"type": "WAIT_FOR_STATE", "state": state}
            if raw.get("targetRef") is not None:
                item["targetRef"] = _target(raw.get("targetRef"))
        else:
            raise MechanicsActionError("Unsupported mechanics action")

        target_ref = item.get("targetRef")
        if (
            allowed_target_refs is not None
            and isinstance(target_ref, str)
            and target_ref not in allowed_target_refs
        ):
            raise MechanicsActionError("Mechanics action references an unobserved target")

        for field in ("answerRef", "secretRef", "verificationRef", "artifactRef", "valueRef"):
            ref_value = item.get(field)
            if (
                allowed_value_refs is not None
                and isinstance(ref_value, str)
                and ref_value not in allowed_value_refs
            ):
                raise MechanicsActionError("Mechanics action references an unavailable local value")

        normalized.append(item)
    return normalized


def validate_legacy_actions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise MechanicsActionError("Legacy fallback must return 1-16 bounded actions")
    result: list[dict[str, object]] = []
    for raw_value in value:
        if not isinstance(raw_value, dict):
            raise MechanicsActionError("Legacy fallback actions must be objects")
        raw = dict(raw_value)
        action_type = str(raw.get("type") or "")
        if action_type in {"FOCUS", "CLICK", "SELECT_EXACT_OPTION"}:
            result.append({"type": action_type})
            continue
        if action_type == "TYPE" and raw.get("valueSource") == "ANSWER":
            result.append({"type": "TYPE", "valueSource": "ANSWER"})
            continue
        if action_type == "KEY" and raw.get("key") in ALLOWED_KEYS:
            result.append({"type": "KEY", "key": str(raw["key"])})
            continue
        if action_type == "WAIT_FOR_STATE" and raw.get("state") in {
            "OPTIONS_VISIBLE",
            "VALUE_COMMITTED",
        }:
            result.append({"type": "WAIT_FOR_STATE", "state": str(raw["state"])})
            continue
        raise MechanicsActionError(
            "Legacy fallback proposed an unsupported or value-bearing action"
        )
    return result
