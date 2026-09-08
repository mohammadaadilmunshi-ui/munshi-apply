"""Signed Apply client for Hunter's private execution/artifact bridge."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from uuid import uuid4

import httpx

REQUEST_VERSION = "munshi-application-execution-request-v1"
RESPONSE_VERSION = "munshi-application-execution-response-v1"
PURPOSE_PLAN_CURRENT = "PLAN_CURRENT"
PURPOSE_ARTIFACT_BYTES = "ARTIFACT_BYTES"


class HunterExecutionBridgeClient:
    def __init__(
        self,
        *,
        base_url: str,
        secret: str,
        tenant_id: str,
        user_id: str,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        base = str(base_url or "").strip().rstrip("/")
        if not base.startswith("http://") and not base.startswith("https://"):
            raise ValueError("Hunter execution bridge base URL is required")
        if len(str(secret or "")) < 16:
            raise ValueError("Hunter execution bridge HMAC secret is required")
        if not tenant_id or not user_id:
            raise ValueError("Hunter execution bridge owner is required")
        self.base_url = base
        self.secret = secret.encode()
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.client = httpx.Client(timeout=timeout_seconds, transport=transport)

    @staticmethod
    def _canonical(value: dict[str, Any]) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

    def _payload(self, plan: dict[str, Any], purpose: str) -> dict[str, Any]:
        resume = dict(plan["resume"])
        return {
            "version": REQUEST_VERSION,
            "request_id": f"execution-request-{uuid4()}",
            "purpose": purpose,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "application_id": str(plan["application_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_digest": str(plan["plan_digest"]),
            "artifact_id": str(resume["artifact_id"]),
            "artifact_reference": str(resume["artifact_reference"]),
            "artifact_sha256": str(resume["artifact_sha256"]),
        }

    def _headers(self, payload: dict[str, Any], body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        digest = hashlib.sha256(body).hexdigest()
        signature = hmac.new(
            self.secret, f"{payload['request_id']}.{timestamp}.{digest}".encode(), hashlib.sha256
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Munshi-Event-Id": str(payload["request_id"]),
            "X-Munshi-Timestamp": timestamp,
            "X-Munshi-Content-SHA256": digest,
            "X-Munshi-Signature": f"sha256={signature}",
        }

    def _verify_response(
        self, *, response: httpx.Response, payload: dict[str, Any], purpose: str
    ) -> bytes:
        if response.status_code != 200:
            raise RuntimeError(
                f"Hunter execution bridge rejected {purpose}: HTTP {response.status_code}"
            )
        body = response.content
        digest = hashlib.sha256(body).hexdigest()
        if response.headers.get("X-Munshi-Response-Event-Id") != payload["request_id"]:
            raise RuntimeError("Hunter execution bridge response identity mismatch")
        if response.headers.get("X-Munshi-Response-Purpose") != purpose:
            raise RuntimeError("Hunter execution bridge response purpose mismatch")
        if response.headers.get("X-Munshi-Response-SHA256") != digest:
            raise RuntimeError("Hunter execution bridge response digest mismatch")
        if response.headers.get("X-Munshi-Plan-Digest") != payload["plan_digest"]:
            raise RuntimeError("Hunter execution bridge response plan digest mismatch")
        expected = hmac.new(
            self.secret,
            f"{payload['request_id']}.{purpose}.{digest}.{payload['plan_digest']}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(
            response.headers.get("X-Munshi-Response-Signature", ""), f"sha256={expected}"
        ):
            raise RuntimeError("Hunter execution bridge response signature mismatch")
        return body

    def plan_is_current(self, plan: dict[str, Any]) -> bool:
        try:
            payload = self._payload(plan, PURPOSE_PLAN_CURRENT)
            body = self._canonical(payload)
            response = self.client.post(
                f"{self.base_url}/api/application-execution/plan-current",
                content=body,
                headers=self._headers(payload, body),
            )
            verified = self._verify_response(
                response=response, payload=payload, purpose=PURPOSE_PLAN_CURRENT
            )
            result = json.loads(verified)
            return (
                result.get("version") == RESPONSE_VERSION
                and result.get("request_id") == payload["request_id"]
                and result.get("plan_id") == payload["plan_id"]
                and result.get("plan_digest") == payload["plan_digest"]
                and result.get("fresh") is True
                and result.get("submission_authority") is False
            )
        except Exception:
            return False

    def artifact_bytes(self, plan: dict[str, Any]) -> bytes:
        payload = self._payload(plan, PURPOSE_ARTIFACT_BYTES)
        body = self._canonical(payload)
        response = self.client.post(
            f"{self.base_url}/api/application-execution/artifact",
            content=body,
            headers=self._headers(payload, body),
        )
        verified = self._verify_response(
            response=response, payload=payload, purpose=PURPOSE_ARTIFACT_BYTES
        )
        expected_sha = str(plan["resume"]["artifact_sha256"])
        if hashlib.sha256(verified).hexdigest() != expected_sha:
            raise RuntimeError("Hunter artifact bytes do not match accepted plan digest")
        if response.headers.get("X-Munshi-Artifact-SHA256") != expected_sha:
            raise RuntimeError("Hunter artifact response digest binding mismatch")
        if response.headers.get("X-Munshi-Submission-Authority") != "false":
            raise RuntimeError("Hunter artifact response carried unexpected submission authority")
        return verified

    def close(self) -> None:
        self.client.close()
