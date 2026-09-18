"""Signed Apply client for Hunter's private execution bridge."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .internal_http_policy import internal_hunter_http_allowed

REQUEST_VERSION = "munshi-application-execution-request-v1"
RESPONSE_VERSION = "munshi-application-execution-response-v1"
PURPOSE_PLAN_CURRENT = "PLAN_CURRENT"
PURPOSE_ARTIFACT_BYTES = "ARTIFACT_BYTES"
PURPOSE_COVER_LETTER_BYTES = "COVER_LETTER_BYTES"
PURPOSE_AUTOAPPLY_CONFIG = "AUTOAPPLY_CONFIG"
PURPOSE_AUTOAPPLY_CREDENTIAL = "AUTOAPPLY_CREDENTIAL"


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
        if not base.startswith(("http://", "https://")):
            raise ValueError("Hunter execution bridge base URL is required")
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            and not internal_hunter_http_allowed(base)
        ):
            raise ValueError("Hunter execution bridge must use HTTPS outside loopback")
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
    def _canonical(v: dict[str, Any]) -> bytes:
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

    @staticmethod
    def _binding(plan: dict[str, Any], purpose: str) -> dict[str, Any]:
        if purpose == PURPOSE_COVER_LETTER_BYTES:
            v = plan.get("cover_letter")
            if not isinstance(v, dict):
                raise ValueError("Application Plan has no cover-letter binding")
            return v
        return dict(plan["resume"])

    def _payload(self, plan: dict[str, Any], purpose: str) -> dict[str, Any]:
        a = self._binding(plan, purpose)
        return {
            "version": REQUEST_VERSION,
            "request_id": f"execution-request-{uuid4()}",
            "purpose": purpose,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "application_id": str(plan["application_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_digest": str(plan["plan_digest"]),
            "artifact_id": str(a["artifact_id"]),
            "artifact_reference": str(a["artifact_reference"]),
            "artifact_sha256": str(a["artifact_sha256"]),
        }

    def _headers(self, p: dict[str, Any], body: bytes) -> dict[str, str]:
        ts = str(int(time.time()))
        d = hashlib.sha256(body).hexdigest()
        sig = hmac.new(
            self.secret, f"{p['request_id']}.{ts}.{d}".encode(), hashlib.sha256
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Munshi-Event-Id": str(p["request_id"]),
            "X-Munshi-Timestamp": ts,
            "X-Munshi-Content-SHA256": d,
            "X-Munshi-Signature": f"sha256={sig}",
        }

    def _verify(self, *, response: httpx.Response, payload: dict[str, Any], purpose: str) -> bytes:
        if response.status_code != 200:
            raise RuntimeError(
                f"Hunter execution bridge rejected {purpose}: HTTP {response.status_code}"
            )
        body = response.content
        d = hashlib.sha256(body).hexdigest()
        if (
            response.headers.get("X-Munshi-Response-Event-Id") != payload["request_id"]
            or response.headers.get("X-Munshi-Response-Purpose") != purpose
            or response.headers.get("X-Munshi-Response-SHA256") != d
            or response.headers.get("X-Munshi-Plan-Digest") != payload["plan_digest"]
        ):
            raise RuntimeError("Hunter execution bridge response digest or binding mismatch")
        exp = hmac.new(
            self.secret,
            f"{payload['request_id']}.{purpose}.{d}.{payload['plan_digest']}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(
            response.headers.get("X-Munshi-Response-Signature", ""), f"sha256={exp}"
        ):
            raise RuntimeError("Hunter execution bridge response signature mismatch")
        return body

    def plan_is_current(self, plan: dict[str, Any]) -> bool:
        try:
            p = self._payload(plan, PURPOSE_PLAN_CURRENT)
            body = self._canonical(p)
            r = self.client.post(
                f"{self.base_url}/api/application-execution/plan-current",
                content=body,
                headers=self._headers(p, body),
            )
            out = json.loads(self._verify(response=r, payload=p, purpose=PURPOSE_PLAN_CURRENT))
            return (
                out.get("version") == RESPONSE_VERSION
                and out.get("request_id") == p["request_id"]
                and out.get("plan_id") == p["plan_id"]
                and out.get("plan_digest") == p["plan_digest"]
                and out.get("fresh") is True
                and out.get("submission_authority") is False
            )
        except Exception:
            return False

    def _artifact(self, plan: dict[str, Any], *, purpose: str, endpoint: str) -> bytes:
        p = self._payload(plan, purpose)
        body = self._canonical(p)
        r = self.client.post(
            f"{self.base_url}{endpoint}", content=body, headers=self._headers(p, body)
        )
        out = self._verify(response=r, payload=p, purpose=purpose)
        a = self._binding(plan, purpose)
        expected = str(a["artifact_sha256"])
        if (
            hashlib.sha256(out).hexdigest() != expected
            or r.headers.get("X-Munshi-Artifact-SHA256") != expected
        ):
            raise RuntimeError("Hunter artifact response digest binding mismatch")
        if r.headers.get("X-Munshi-Submission-Authority") != "false":
            raise RuntimeError("Hunter artifact response carried unexpected submission authority")
        return out

    def artifact_bytes(self, plan: dict[str, Any]) -> bytes:
        return self._artifact(
            plan, purpose=PURPOSE_ARTIFACT_BYTES, endpoint="/api/application-execution/artifact"
        )

    def cover_letter_bytes(self, plan: dict[str, Any]) -> bytes:
        return self._artifact(
            plan,
            purpose=PURPOSE_COVER_LETTER_BYTES,
            endpoint="/api/application-execution/cover-letter",
        )

    def autoapply_config(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Fetch non-secret AutoApply preferences bound to the exact plan."""
        purpose = PURPOSE_AUTOAPPLY_CONFIG
        p = self._payload(plan, purpose)
        body = self._canonical(p)
        response = self.client.post(
            f"{self.base_url}/api/application-execution/autoapply-config",
            content=body,
            headers=self._headers(p, body),
        )
        raw = self._verify(response=response, payload=p, purpose=purpose)
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Hunter AutoApply config response is invalid JSON") from error
        config = decoded.get("config") if isinstance(decoded, dict) else None
        if (
            not isinstance(config, dict)
            or decoded.get("version") != RESPONSE_VERSION
            or decoded.get("request_id") != p["request_id"]
            or decoded.get("purpose") != purpose
            or decoded.get("plan_id") != p["plan_id"]
            or decoded.get("plan_digest") != p["plan_digest"]
        ):
            raise RuntimeError("Hunter AutoApply config response binding mismatch")
        return dict(config)

    def anthropic_api_key(self, plan: dict[str, Any]) -> str:
        """Resolve the dashboard-vault Anthropic key only inside Apply.

        Hunter AES-GCM encrypts the credential response with a per-request key
        derived from the already-shared execution-bridge HMAC secret. This keeps
        the key confidential even when an explicitly configured private Docker
        bridge uses HTTP instead of TLS.
        """
        purpose = PURPOSE_AUTOAPPLY_CREDENTIAL
        p = self._payload(plan, purpose)
        body = self._canonical(p)
        response = self.client.post(
            f"{self.base_url}/api/application-execution/autoapply-credential",
            content=body,
            headers=self._headers(p, body),
        )
        envelope = self._verify(response=response, payload=p, purpose=purpose)
        if (
            response.headers.get("X-Munshi-Credential-Type")
            != "autoapply_anthropic_api_key"
            or response.headers.get("X-Munshi-Credential-Encryption") != "aes-gcm-v1"
            or response.headers.get("X-Munshi-Submission-Authority") != "false"
        ):
            raise RuntimeError("Hunter AutoApply credential response binding mismatch")
        if len(envelope) < 29 or len(envelope) > 16448:
            raise RuntimeError("Hunter AutoApply credential envelope is invalid")

        nonce, ciphertext = envelope[:12], envelope[12:]
        key = hmac.new(
            self.secret,
            (
                f"autoapply-credential:{p['request_id']}:{p['plan_digest']}"
            ).encode("utf-8"),
            hashlib.sha256,
        ).digest()
        aad = (
            f"{p['request_id']}.{p['plan_digest']}.autoapply_anthropic_api_key"
        ).encode("utf-8")
        try:
            raw = AESGCM(key).decrypt(nonce, ciphertext, aad)
            value = raw.decode("utf-8").strip()
        except Exception as error:
            raise RuntimeError(
                "Hunter AutoApply credential envelope could not be decrypted"
            ) from error
        if not value or len(value) > 16384:
            raise RuntimeError("Hunter AutoApply credential is unavailable")
        return value

    def close(self) -> None:
        self.client.close()
