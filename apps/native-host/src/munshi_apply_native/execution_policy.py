"""Fail-closed execution policy, separate from browser mechanics and persistence."""

from __future__ import annotations

from typing import Any


def prepare_permissions(plan: dict[str, Any]) -> dict[str, bool]:
    """Return the explicit permissions required before hosted preparation."""
    permissions = plan.get("permissions")
    required = ("background_prepare", "resume_upload", "normal_answer_autofill")
    if not isinstance(permissions, dict) or any(
        not isinstance(permissions.get(name), bool) for name in required
    ):
        raise ValueError("Application Plan preparation permissions are invalid")
    if permissions["background_prepare"] is not True or permissions["resume_upload"] is not True:
        raise ValueError("Application Plan does not permit hosted preparation")
    if isinstance(plan.get("cover_letter"), dict) and (
        permissions.get("cover_letter_upload") is not True
    ):
        raise ValueError("Application Plan does not permit cover-letter upload")
    return permissions


def safe_evidence(value: Any) -> Any:
    """Reject secrets recursively and redact explicitly sensitive display values."""
    forbidden = {
        "password",
        "passcode",
        "otp",
        "token",
        "oauth_token",
        "access_token",
        "refresh_token",
        "api_key",
        "authorization",
        "authorization_header",
        "hmac_secret",
        "cookie",
        "cookies",
        "secret",
        "execution_value",
    }
    if isinstance(value, list):
        return [safe_evidence(item) for item in value]
    if not isinstance(value, dict):
        return value
    if forbidden.intersection(str(key).casefold() for key in value):
        raise ValueError("Execution evidence contains a prohibited secret field")
    result = {str(key): safe_evidence(item) for key, item in value.items()}
    if str(result.get("sensitivity_class", "NORMAL")).upper() != "NORMAL":
        for key in ("display_value", "value", "answer"):
            if key in result:
                result[key] = "[protected value]"
    return result


def verify_submission_observation(result: dict[str, Any], plan: dict[str, Any]) -> bool:
    evidence = result.get("success_evidence")
    if not isinstance(evidence, dict):
        return False
    if str(evidence.get("job_id", "")) != str(plan["job"]["id"]):
        return False
    if evidence.get("exact_action_verified") is not True:
        return False
    if evidence.get("post_submit_state_changed") is not True:
        return False
    submission_reference = str(
        evidence.get("submission_reference")
        or result.get("submission_reference")
        or ""
    ).strip()
    if not submission_reference:
        return False
    response_status = evidence.get("response_status")
    response_url = str(evidence.get("response_url") or "").strip()
    submit_action = str(evidence.get("submit_action") or "").strip()
    submit_method = str(evidence.get("submit_method") or "").strip().upper()
    action_binding_digest = str(evidence.get("action_binding_digest") or "").strip().casefold()
    confirmation_digest = str(
        evidence.get("confirmation_evidence_digest") or ""
    ).strip().casefold()
    if not isinstance(response_status, int) or not 200 <= response_status < 400:
        return False
    if submit_method != "POST" or not submit_action or response_url != submit_action:
        return False
    for value in (action_binding_digest, confirmation_digest):
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            return False
    return bool(
        evidence.get("completion_marker")
        and evidence.get("submission_response_marker")
        == "exact-approved-action-response"
    )


def validate_submit_observation(
    observation: dict[str, Any], plan: dict[str, Any], review: dict[str, Any]
) -> None:
    if observation.get("security_checkpoint"):
        raise ValueError("Security checkpoint blocks submission")
    if observation.get("plan_current") is not True:
        raise ValueError("Current Hunter plan validation is required")
    if str(observation.get("job_id", "")) != str(plan["job"]["id"]):
        raise ValueError("Browser job changed after review")
    if observation.get("current_url") != review["destination_url"]:
        raise ValueError("Browser destination changed after review")
    if observation.get("form_digest") != review["browser_verification"]["form_digest"]:
        raise ValueError("Browser form changed after review")
    submit_binding = observation.get("submit_binding")
    if not isinstance(submit_binding, dict):
        raise ValueError("Browser submit action is not deterministically bound")
    if str(submit_binding.get("method") or "").upper() != "POST":
        raise ValueError("Browser submit action must be an exact reviewed POST")
    binding_digest = str(submit_binding.get("binding_digest") or "").strip().casefold()
    if len(binding_digest) != 64 or any(
        character not in "0123456789abcdef" for character in binding_digest
    ):
        raise ValueError("Browser submit binding digest is invalid")
    if observation.get("resume_uploaded") is not True or (
        observation.get("resume_sha256") != plan["resume"]["artifact_sha256"]
    ):
        raise ValueError("Browser resume changed after review")
    cover_letter = plan.get("cover_letter")
    if isinstance(cover_letter, dict) and (
        observation.get("cover_letter_uploaded") is not True
        or observation.get("cover_letter_sha256") != cover_letter.get("artifact_sha256")
    ):
        raise ValueError("Browser cover letter changed after review")
    if observation.get("unresolved") or observation.get("validation_errors"):
        raise ValueError("Browser form has unresolved required inputs")
    if observation.get("completed_required_fields") != observation.get("required_fields"):
        raise ValueError("Browser form required fields are incomplete")
