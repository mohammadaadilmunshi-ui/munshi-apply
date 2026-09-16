from __future__ import annotations

from typing import Any

from .account_teach_service import AccountTeachService
from .ats_account_lifecycle import ATSAccountLifecycle
from .database import Database


_ACCOUNT_MESSAGE_TYPES = {
    "PROVISION_ATS_ACCOUNT",
    "BEGIN_ATS_ACCOUNT_CREATION",
    "MARK_ATS_ACCOUNT_CREATED",
    "BIND_ATS_ACCOUNT_CONTINUATION",
    "START_ATS_EMAIL_VERIFICATION",
    "MARK_ATS_EMAIL_VERIFICATION_READY",
    "CLAIM_ATS_EMAIL_VERIFICATION",
    "REQUEUE_ATS_EMAIL_VERIFICATION",
    "CONSUME_ATS_EMAIL_VERIFICATION",
    "MARK_ATS_ACCOUNT_VERIFIED",
    "MARK_ATS_ACCOUNT_AUTHENTICATED",
    "MARK_ATS_ACCOUNT_SECURITY_ISSUE",
    "MARK_ATS_CONTINUATION_READY",
    "CONSUME_ATS_CONTINUATION",
    "GET_ATS_ACCOUNT_STATE",
    "CAPTURE_ATS_ACCOUNT_TEACH_LESSON",
    "DRAIN_ATS_ACCOUNT_TEACH_LESSONS",
    "GET_PROMOTED_ATS_ACCOUNT_RECIPE",
    "RECORD_ATS_ACCOUNT_RECIPE_OUTCOME",
}


def _payload(message: dict[str, object], label: str) -> dict[str, Any]:
    value = message.get("payload")
    if not isinstance(value, dict):
        raise ValueError(f"{label} payload must be an object")
    return value


def _text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} requires {key}")
    return value.strip()


def handle_account_message(
    message: dict[str, object],
    database: Database,
) -> dict[str, object] | None:
    message_type = message.get("type")
    if message_type not in _ACCOUNT_MESSAGE_TYPES:
        return None

    lifecycle = ATSAccountLifecycle(database)
    if message_type == "PROVISION_ATS_ACCOUNT":
        return {"ok": True, "data": lifecycle.provision(message.get("payload"))}
    if message_type == "BEGIN_ATS_ACCOUNT_CREATION":
        payload = _payload(message, "ATS account creation")
        return {
            "ok": True,
            "data": lifecycle.begin_creation(
                _text(payload, "accountId", "ATS account creation"),
                _text(payload, "observedAt", "ATS account creation"),
            ),
        }
    if message_type == "MARK_ATS_ACCOUNT_CREATED":
        payload = _payload(message, "ATS account created")
        verification_required = payload.get("verificationRequired")
        if not isinstance(verification_required, bool):
            raise ValueError("ATS account created requires boolean verificationRequired")
        return {
            "ok": True,
            "data": lifecycle.mark_created(
                _text(payload, "accountId", "ATS account created"),
                _text(payload, "applicationId", "ATS account created"),
                _text(payload, "observedAt", "ATS account created"),
                verification_required=verification_required,
            ),
        }
    if message_type == "BIND_ATS_ACCOUNT_CONTINUATION":
        return {"ok": True, "data": lifecycle.bind_continuation(message.get("payload"))}
    if message_type == "START_ATS_EMAIL_VERIFICATION":
        return {"ok": True, "data": lifecycle.start_verification(message.get("payload"))}
    if message_type == "MARK_ATS_EMAIL_VERIFICATION_READY":
        return {
            "ok": True,
            "data": lifecycle.mark_verification_ready(message.get("payload")),
        }
    if message_type in {
        "CLAIM_ATS_EMAIL_VERIFICATION",
        "REQUEUE_ATS_EMAIL_VERIFICATION",
        "CONSUME_ATS_EMAIL_VERIFICATION",
    }:
        payload = _payload(message, "ATS email verification")
        challenge_id = _text(payload, "challengeId", "ATS email verification")
        observed_at = _text(payload, "observedAt", "ATS email verification")
        if message_type == "CLAIM_ATS_EMAIL_VERIFICATION":
            data = lifecycle.claim_verification(challenge_id, observed_at)
        elif message_type == "REQUEUE_ATS_EMAIL_VERIFICATION":
            data = lifecycle.requeue_claim(challenge_id, observed_at)
        else:
            data = lifecycle.consume_verification(challenge_id, observed_at)
        return {"ok": True, "data": data}
    if message_type in {"MARK_ATS_ACCOUNT_VERIFIED", "MARK_ATS_ACCOUNT_AUTHENTICATED"}:
        payload = _payload(message, "ATS account transition")
        account_id = _text(payload, "accountId", "ATS account transition")
        application_id = _text(payload, "applicationId", "ATS account transition")
        observed_at = _text(payload, "observedAt", "ATS account transition")
        data = (
            lifecycle.mark_verified(account_id, application_id, observed_at)
            if message_type == "MARK_ATS_ACCOUNT_VERIFIED"
            else lifecycle.mark_authenticated(account_id, application_id, observed_at)
        )
        return {"ok": True, "data": data}
    if message_type == "MARK_ATS_ACCOUNT_SECURITY_ISSUE":
        return {"ok": True, "data": lifecycle.security_issue(message.get("payload"))}
    if message_type in {"MARK_ATS_CONTINUATION_READY", "CONSUME_ATS_CONTINUATION"}:
        payload = _payload(message, "ATS continuation")
        continuation_id = _text(payload, "continuationId", "ATS continuation")
        observed_at = _text(payload, "observedAt", "ATS continuation")
        data = (
            lifecycle.mark_continuation_ready(continuation_id, observed_at)
            if message_type == "MARK_ATS_CONTINUATION_READY"
            else lifecycle.consume_continuation(continuation_id, observed_at)
        )
        return {"ok": True, "data": data}
    if message_type == "GET_ATS_ACCOUNT_STATE":
        payload = _payload(message, "ATS account state")
        return {
            "ok": True,
            "data": lifecycle.snapshot(_text(payload, "accountId", "ATS account state")),
        }

    teach = AccountTeachService(database)
    if message_type == "CAPTURE_ATS_ACCOUNT_TEACH_LESSON":
        return {"ok": True, "data": teach.capture(message.get("payload"))}
    if message_type == "DRAIN_ATS_ACCOUNT_TEACH_LESSONS":
        payload = message.get("payload")
        limit = 20
        if payload is not None:
            if not isinstance(payload, dict):
                raise ValueError("ATS account Teach drain payload must be an object")
            raw_limit = payload.get("limit", 20)
            if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
                raise ValueError("ATS account Teach drain limit must be an integer")
            limit = raw_limit
        return {"ok": True, "data": teach.drain(limit=limit)}
    if message_type == "GET_PROMOTED_ATS_ACCOUNT_RECIPE":
        return {"ok": True, "data": teach.lookup_promoted(message.get("payload"))}

    payload = _payload(message, "ATS account recipe outcome")
    success = payload.get("success")
    if not isinstance(success, bool):
        raise ValueError("ATS account recipe outcome requires boolean success")
    failure_reason = payload.get("failureReason")
    if failure_reason is not None and not isinstance(failure_reason, str):
        raise ValueError("ATS account recipe outcome failureReason must be a string")
    return {
        "ok": True,
        "data": teach.record_verified_outcome(
            _text(payload, "recipeId", "ATS account recipe outcome"),
            application_id=(
                _text(payload, "applicationId", "ATS account recipe outcome")
                if payload.get("applicationId") is not None
                else None
            ),
            success=success,
            occurred_at=_text(payload, "occurredAt", "ATS account recipe outcome"),
            failure_reason=failure_reason,
        ),
    }
