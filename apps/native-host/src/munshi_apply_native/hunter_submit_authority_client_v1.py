"""Authenticated Hunter READ/CLAIM client for canonical submit authority."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

REQUEST_VERSION = "munshi-application-execution-request-v1"
RESPONSE_VERSION = "munshi-application-execution-response-v1"
PURPOSE_READ = "SUBMIT_AUTHORIZATION_READ"
PURPOSE_CLAIM = "SUBMIT_AUTHORIZATION_CLAIM"


class SubmitAuthorizationClientError(RuntimeError):
    pass


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def _expected_claim_digest(
    envelope: Mapping[str, Any], claimant_id: str
) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "authorization_id": envelope["authorization_id"],
                "authority_digest": envelope["authority_digest"],
                "claimant_id": claimant_id,
                "generation": int(envelope["generation"]),
            }
        )
    ).hexdigest()


class HunterSubmitAuthorityClient:
    def __init__(self, *, base_url: str, secret: str, timeout: float = 10.0) -> None:
        self.base_url = str(base_url).strip().rstrip("/")
        self.secret = str(secret)
        self.timeout = float(timeout)
        if not self.base_url:
            raise SubmitAuthorizationClientError("Hunter base URL is not configured")
        if not (
            self.base_url.startswith("https://")
            or self.base_url.startswith("http://127.0.0.1")
            or self.base_url.startswith("http://localhost")
        ):
            raise SubmitAuthorizationClientError(
                "Hunter control endpoint must use HTTPS except on localhost"
            )
        if len(self.secret) < 16:
            raise SubmitAuthorizationClientError(
                "Apply handoff HMAC secret is not configured"
            )

    @classmethod
    def from_environment(cls) -> "HunterSubmitAuthorityClient":
        return cls(
            base_url=str(
                os.getenv("MUNSHI_HUNTER_BASE_URL")
                or os.getenv("MUNSHI_HUNTER_EXECUTION_BRIDGE_BASE_URL")
                or ""
            ),
            secret=str(os.getenv("MUNSHI_APPLY_HANDOFF_HMAC_SECRET") or ""),
        )

    def _request(
        self,
        *,
        purpose: str,
        binding: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        event_id = f"submit-authority-{purpose.casefold()}-{uuid4()}"
        plan_digest = str(binding.get("plan_digest") or "")
        request_value = {
            "version": REQUEST_VERSION,
            "request_id": event_id,
            "purpose": purpose,
            "tenant_id": binding.get("tenant_id"),
            "user_id": binding.get("user_id"),
            "application_id": binding.get("application_id"),
            "plan_id": binding.get("plan_id"),
            "plan_digest": plan_digest,
            "payload": dict(payload),
        }
        body = _canonical(request_value)
        body_digest = hashlib.sha256(body).hexdigest()
        timestamp = str(int(time.time()))
        signature = hmac.new(
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
                "X-Munshi-Signature": f"sha256={signature}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read()
                headers = dict(response.headers.items())
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise SubmitAuthorizationClientError(
                f"Hunter {purpose} response is unavailable"
            ) from error

        response_digest = hashlib.sha256(raw).hexdigest()

        def header(name: str) -> str:
            return next(
                (
                    str(value)
                    for key, value in headers.items()
                    if str(key).casefold() == name.casefold()
                ),
                "",
            )

        expected_signature = hmac.new(
            self.secret.encode(),
            f"{event_id}.{purpose}.{response_digest}.{plan_digest}".encode(),
            hashlib.sha256,
        ).hexdigest()
        checks = (
            header("X-Munshi-Response-Event-Id") == event_id,
            header("X-Munshi-Response-Purpose") == purpose,
            header("X-Munshi-Response-SHA256") == response_digest,
            header("X-Munshi-Plan-Digest") == plan_digest,
            hmac.compare_digest(
                header("X-Munshi-Response-Signature"),
                f"sha256={expected_signature}",
            ),
        )
        if not all(checks):
            raise SubmitAuthorizationClientError(
                f"Hunter {purpose} response binding is invalid"
            )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SubmitAuthorizationClientError(
                f"Hunter {purpose} response is invalid JSON"
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("version") != RESPONSE_VERSION
            or value.get("request_id") != event_id
            or value.get("purpose") != purpose
            or value.get("plan_digest") != plan_digest
            or not isinstance(value.get("result"), dict)
        ):
            raise SubmitAuthorizationClientError(
                f"Hunter {purpose} response payload is invalid"
            )
        return dict(value["result"])

    @staticmethod
    def _binding(value: Mapping[str, Any]) -> dict[str, Any]:
        required = (
            "tenant_id",
            "user_id",
            "application_id",
            "plan_id",
            "session_id",
            "plan_digest",
        )
        result = {key: value.get(key) for key in required}
        if any(not str(result[key] or "").strip() for key in required):
            raise SubmitAuthorizationClientError(
                "Submit authority binding is incomplete"
            )
        return result

    def read(self, binding: Mapping[str, Any]) -> dict[str, Any]:
        exact = self._binding(binding)
        result = self._request(
            purpose=PURPOSE_READ,
            binding=exact,
            payload=exact,
        )
        if (
            result.get("status") != "ISSUED"
            or result.get("submission_authority") is not True
            or any(str(result.get(key) or "") != str(exact[key]) for key in exact)
        ):
            raise SubmitAuthorizationClientError(
                "Hunter did not return the exact ISSUED submit authority"
            )
        return result

    def claim(
        self,
        envelope: Mapping[str, Any],
        *,
        claimant_id: str,
    ) -> dict[str, Any]:
        exact = self._binding(envelope)
        claimant = str(claimant_id or "").strip()
        if not claimant:
            raise SubmitAuthorizationClientError("Durable claimant id is required")
        result = self._request(
            purpose=PURPOSE_CLAIM,
            binding=exact,
            payload={"authorization": dict(envelope), "claimant_id": claimant},
        )
        expected_digest = _expected_claim_digest(envelope, claimant)
        if (
            result.get("status") not in {"CLAIMED", "CONSUMED"}
            or result.get("submission_authority") is not True
            or result.get("authorization_id") != envelope.get("authorization_id")
            or result.get("authority_digest") != envelope.get("authority_digest")
            or result.get("claim_digest") != expected_digest
            or int(result.get("generation") or 0) != int(envelope.get("generation") or 0)
            or (
                result.get("status") == "CONSUMED"
                and result.get("replayed") is not True
            )
        ):
            raise SubmitAuthorizationClientError(
                "Hunter did not return the exact one-use submit claim"
            )
        return result
