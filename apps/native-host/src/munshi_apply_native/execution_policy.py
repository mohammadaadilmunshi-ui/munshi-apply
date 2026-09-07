"""Fail-closed execution policy, separate from browser mechanics and persistence."""
from __future__ import annotations

from typing import Any


def safe_evidence(value: Any) -> Any:
    """Reject secrets recursively and redact explicitly sensitive display values."""
    forbidden = {
        "password", "passcode", "otp", "token", "oauth_token", "access_token",
        "refresh_token", "api_key", "authorization", "authorization_header",
        "hmac_secret", "cookie", "cookies", "secret", "execution_value",
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
    # URL changes, clicks, and arbitrary DOM mutations do not prove completion.
    return bool(evidence.get("completion_marker") and (
        evidence.get("confirmation_message") or evidence.get("provider_application_id")
    ))


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
    if observation.get("unresolved") or observation.get("validation_errors"):
        raise ValueError("Browser form has unresolved required inputs")
    if observation.get("completed_required_fields") != observation.get("required_fields"):
        raise ValueError("Browser form required fields are incomplete")
