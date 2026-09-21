"""Strict verified production receipt creation and authenticated Hunter handoff."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .internal_http_policy import internal_hunter_http_allowed

RECEIPT_VERSION = "munshi-production-submission-receipt-v1"
REQUEST_VERSION = "munshi-application-execution-request-v1"
RESPONSE_VERSION = "munshi-application-execution-response-v1"
PURPOSE = "PRODUCTION_RECEIPT_INGEST"


class ProductionReceiptError(RuntimeError):
    pass


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def _text(value: Any, label: str) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        raise ProductionReceiptError(f"{label} is required")
    return normalized


def _digest(value: Any, label: str) -> str:
    normalized = str(value or "").strip().casefold()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise ProductionReceiptError(f"{label} is not a SHA-256 digest")
    return normalized


def build_verified_receipt(
    *,
    authorization: Mapping[str, Any],
    claim: Mapping[str, Any],
    execution: Mapping[str, Any],
    provider_observation: Mapping[str, Any],
    verified_at: str | None = None,
) -> dict[str, Any]:
    auth, claimed = dict(authorization), dict(claim)
    result, proof = dict(execution), dict(provider_observation)
    if auth.get("synthetic") is not False or auth.get("submission_authority") is not True:
        raise ProductionReceiptError("Production authority flags are invalid")
    if claimed.get("status") != "CLAIMED" or claimed.get("submission_authority") is not True:
        raise ProductionReceiptError("A one-time canonical authority claim is required")
    if (
        claimed.get("authorization_id") != auth.get("authorization_id")
        or claimed.get("authority_digest") != auth.get("authority_digest")
    ):
        raise ProductionReceiptError("Authority claim does not match authorization")
    if result.get("status") != "COMPLETED" or result.get("claimed_submission") is not True:
        raise ProductionReceiptError("Browser execution is not a completed submission")
    if (
        str(result.get("plan_id") or "") != str(auth.get("plan_id") or "")
        or str(result.get("plan_digest") or "") != str(auth.get("plan_digest") or "")
        or str(result.get("provider") or "").upper()
        != str(auth.get("provider") or "").upper()
    ):
        raise ProductionReceiptError("Execution binding does not match authorization")

    observation = result.get("submission_observation")
    if not isinstance(observation, Mapping):
        raise ProductionReceiptError("Exact reviewed submission observation is required")
    observed = dict(observation)
    reviewed_destination = _text(
        observed.get("reviewed_destination"),
        "Reviewed destination",
    )
    if reviewed_destination != str(auth.get("target_url") or ""):
        raise ProductionReceiptError("Submission destination does not match authorization")
    submit_method = str(observed.get("method") or "").upper()
    submit_action = _text(observed.get("action"), "Submit action")
    response_url = _text(observed.get("response_url"), "Submit response URL")
    response_status = observed.get("response_status")
    if (
        submit_method not in {"POST", "PUT", "PATCH"}
        or observed.get("exact_action_verified") is not True
        or response_url != submit_action
        or not isinstance(response_status, int)
        or not 200 <= response_status < 400
    ):
        raise ProductionReceiptError(
            "Exact reviewed mutating response evidence is required"
        )
    action_binding_digest = _digest(
        observed.get("action_binding_digest"),
        "Action binding digest",
    )
    confirmation_evidence_digest = _digest(
        observed.get("confirmation_evidence_digest"),
        "Confirmation evidence digest",
    )
    submission_reference = _text(
        result.get("submission_reference")
        or observed.get("submission_reference"),
        "Submission reference",
    )
    provider_id = _text(
        result.get("provider_application_id")
        or observed.get("provider_application_id")
        or submission_reference,
        "Provider application id",
    )

    verification_method: str
    evidence_material: dict[str, Any]
    if proof.get("lookup_confirmed") is True:
        if (
            _text(proof.get("provider_application_id"), "Verified provider application id")
            != provider_id
            or str(proof.get("provider") or "").upper()
            != str(auth.get("provider") or "").upper()
            or str(proof.get("target_url") or "") != str(auth.get("target_url") or "")
        ):
            raise ProductionReceiptError("Independent provider lookup is not correlated")
        verification_method = "INDEPENDENT_PROVIDER_LOOKUP"
        evidence_material = {
            "verification_method": verification_method,
            "provider": str(proof["provider"]).upper(),
            "provider_application_id": provider_id,
            "target_url": str(proof["target_url"]),
            "external_observation_id": _text(
                proof.get("external_observation_id"),
                "Independent observation id",
            ),
            "lookup_confirmed": True,
            "observed_status": _text(
                proof.get("observed_status"),
                "Observed provider status",
            ),
        }
    else:
        if (
            proof.get("exact_action_confirmed") is not True
            or str(proof.get("provider") or "").upper()
            != str(auth.get("provider") or "").upper()
            or str(proof.get("target_url") or "") != str(auth.get("target_url") or "")
            or str(proof.get("submit_action") or "") != submit_action
            or str(proof.get("submit_method") or "").upper() != submit_method
            or str(proof.get("response_url") or "") != response_url
            or proof.get("response_status") != response_status
            or str(proof.get("action_binding_digest") or "").casefold()
            != action_binding_digest
            or str(proof.get("confirmation_evidence_digest") or "").casefold()
            != confirmation_evidence_digest
            or _text(
                proof.get("provider_application_id")
                or proof.get("submission_reference"),
                "Verified submission reference",
            )
            != provider_id
        ):
            raise ProductionReceiptError("Exact-action browser proof is not correlated")
        verification_method = "EXACT_APPROVED_ACTION_RESPONSE_AND_CONFIRMATION"
        evidence_material = {
            "verification_method": verification_method,
            "provider": str(auth.get("provider") or "").upper(),
            "provider_application_id": provider_id,
            "submission_reference": submission_reference,
            "target_url": reviewed_destination,
            "submit_action": submit_action,
            "submit_method": submit_method,
            "response_status": response_status,
            "response_url": response_url,
            "action_binding_digest": action_binding_digest,
            "confirmation_evidence_digest": confirmation_evidence_digest,
            "external_observation_id": _text(
                proof.get("external_observation_id"),
                "Browser evidence id",
            ),
            "exact_action_confirmed": True,
            "observed_status": _text(
                proof.get("observed_status"),
                "Observed submission status",
            ),
        }

    evidence_digest = hashlib.sha256(_canonical(evidence_material)).hexdigest()
    material = {
        "version": RECEIPT_VERSION,
        "tenant_id": _text(auth.get("tenant_id"), "Tenant id"),
        "user_id": _text(auth.get("user_id"), "User id"),
        "application_id": _text(auth.get("application_id"), "Application id"),
        "authorization_id": _text(auth.get("authorization_id"), "Authorization id"),
        "authority_digest": _digest(auth.get("authority_digest"), "Authority digest"),
        "claim_digest": _digest(claimed.get("claim_digest"), "Claim digest"),
        "plan_id": _text(auth.get("plan_id"), "Plan id"),
        "plan_digest": _digest(auth.get("plan_digest"), "Plan digest"),
        "session_id": _text(auth.get("session_id"), "Session id"),
        "review_id": _text(auth.get("review_id"), "Review id"),
        "approval_id": _text(auth.get("approval_id"), "Approval id"),
        "provider": str(auth.get("provider") or "").upper(),
        "provider_application_id": provider_id,
        "target_url": _text(auth.get("target_url"), "Target URL"),
        "verification_method": verification_method,
        "verification_evidence_digest": evidence_digest,
        "verified_at": (
            verified_at
            if isinstance(verified_at, str) and verified_at.strip()
            else datetime.now(UTC).isoformat().replace("+00:00", "Z")
        ),
        "synthetic": False,
        "verification_status": "VERIFIED",
    }
    receipt_digest = hashlib.sha256(_canonical(material)).hexdigest()
    receipt_id = "production-receipt-" + receipt_digest[:32]
    secret = str(os.getenv("MUNSHI_PRODUCTION_RECEIPT_HMAC_SECRET") or "")
    if len(secret) < 32:
        raise ProductionReceiptError("Production receipt HMAC secret is not configured")
    signature = hmac.new(
        secret.encode(), receipt_digest.encode(), hashlib.sha256
    ).hexdigest()
    return {
        **material,
        "receipt_id": receipt_id,
        "receipt_digest": receipt_digest,
        "signature": f"sha256={signature}",
    }


class ProductionReceiptClient:
    def __init__(self, *, base_url: str, secret: str, timeout: float = 10.0) -> None:
        self.base_url = str(base_url).strip().rstrip("/")
        self.secret = str(secret)
        self.timeout = float(timeout)
        if not self.base_url or not (
            self.base_url.startswith("https://")
            or self.base_url.startswith("http://127.0.0.1")
            or self.base_url.startswith("http://localhost")
            or internal_hunter_http_allowed(self.base_url)
        ):
            raise ProductionReceiptError(
                "Hunter receipt endpoint must use HTTPS except localhost "
                "or the explicit configured internal target bridge"
            )
        if len(self.secret) < 16:
            raise ProductionReceiptError("Apply handoff HMAC secret is not configured")

    @classmethod
    def from_environment(cls) -> "ProductionReceiptClient":
        return cls(
            base_url=str(
                os.getenv("MUNSHI_HUNTER_BASE_URL")
                or os.getenv("MUNSHI_HUNTER_EXECUTION_BRIDGE_BASE_URL")
                or ""
            ),
            secret=str(os.getenv("MUNSHI_APPLY_HANDOFF_HMAC_SECRET") or ""),
        )

    def ingest(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(receipt)
        event_id = f"receipt-ingest-{uuid4()}"
        plan_digest = str(value.get("plan_digest") or "")
        request_value = {
            "version": REQUEST_VERSION,
            "request_id": event_id,
            "purpose": PURPOSE,
            "tenant_id": value.get("tenant_id"),
            "user_id": value.get("user_id"),
            "application_id": value.get("application_id"),
            "plan_id": value.get("plan_id"),
            "plan_digest": plan_digest,
            "payload": {"receipt": value},
        }
        body = _canonical(request_value)
        body_digest = hashlib.sha256(body).hexdigest()
        timestamp = str(int(time.time()))
        request_signature = hmac.new(
            self.secret.encode(),
            f"{event_id}.{timestamp}.{body_digest}".encode(),
            hashlib.sha256,
        ).hexdigest()
        request = urllib.request.Request(  # noqa: S310
            self.base_url + "/api/application-execution/plan-current",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Munshi-Event-Id": event_id,
                "X-Munshi-Timestamp": timestamp,
                "X-Munshi-Content-SHA256": body_digest,
                "X-Munshi-Signature": f"sha256={request_signature}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read()
                headers = dict(response.headers.items())
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProductionReceiptError("Hunter receipt response is unavailable") from error
        response_digest = hashlib.sha256(raw).hexdigest()

        def header(name: str) -> str:
            return next(
                (
                    str(item)
                    for key, item in headers.items()
                    if str(key).casefold() == name.casefold()
                ),
                "",
            )

        expected = hmac.new(
            self.secret.encode(),
            f"{event_id}.{PURPOSE}.{response_digest}.{plan_digest}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not all(
            (
                header("X-Munshi-Response-Event-Id") == event_id,
                header("X-Munshi-Response-Purpose") == PURPOSE,
                header("X-Munshi-Response-SHA256") == response_digest,
                header("X-Munshi-Plan-Digest") == plan_digest,
                hmac.compare_digest(
                    header("X-Munshi-Response-Signature"), f"sha256={expected}"
                ),
            )
        ):
            raise ProductionReceiptError("Hunter receipt response binding is invalid")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ProductionReceiptError("Hunter receipt response is invalid JSON") from error
        result = payload.get("result") if isinstance(payload, dict) else None
        if (
            not isinstance(result, dict)
            or result.get("status") != "INGESTED"
            or result.get("verification_status") != "VERIFIED"
            or result.get("receipt_id") != value.get("receipt_id")
        ):
            raise ProductionReceiptError("Hunter did not acknowledge exact receipt")
        return dict(result)
