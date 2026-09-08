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
    if evidence.get("provider") != plan["provider_policy"]["provider"]:
        return False
    if str(evidence.get("job_id", "")) != str(plan["job"]["id"]):
        return False
    # URL changes, clicks, HTTP success alone, and generic DOM success text do not prove completion.
    provider_application_id = str(evidence.get("provider_application_id") or "").strip()
    response_status = evidence.get("response_status")
    response_url = str(evidence.get("response_url") or "").strip()
    submit_action = str(evidence.get("submit_action") or "").strip()
    submit_method = str(evidence.get("submit_method") or "").strip().upper()
    if not provider_application_id:
        return False
    if not isinstance(response_status, int) or not 200 <= response_status < 300:
        return False
    if submit_method != "POST" or not submit_action or response_url != submit_action:
        return False
    return bool(evidence.get("completion_marker") and evidence.get("submission_response_marker"))


def validate_submit_observation(
    observation: dict[str, Any], plan: dict[str, Any], review: dict[str, Any]
) -> None:
    if observation.get("security_checkpoint"):
        raise ValueError("Security checkpoint blocks submission")
    if observation.get("supported") is not True:
        raise ValueError("Provider final submission is unsupported")
    if observation.get("plan_current") is not True:
        raise ValueError("Current Hunter plan validation is required")
    if observation.get("provider") != plan["provider_policy"]["provider"]:
        raise ValueError("Browser provider changed after review")
    if str(observation.get("job_id", "")) != str(plan["job"]["id"]):
        raise ValueError("Browser job changed after review")
    if observation.get("current_url") != review["destination_url"]:
        raise ValueError("Browser destination changed after review")
    if observation.get("form_digest") != review["browser_verification"]["form_digest"]:
        raise ValueError("Browser form changed after review")
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
