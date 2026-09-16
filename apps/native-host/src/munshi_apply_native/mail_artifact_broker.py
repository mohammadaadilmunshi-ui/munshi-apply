from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import httpx


class MailArtifactBrokerError(RuntimeError):
    pass


_ALLOWED_ARTIFACT_KINDS = {
    "EMAIL_VERIFICATION_CODE",
    "EMAIL_VERIFICATION_LINK",
    "PASSWORD_RESET_LINK",
    "MAGIC_LOGIN_LINK",
}


@dataclass(frozen=True)
class ClaimedMailArtifact:
    request_id: str
    artifact_kind: str
    artifact_digest: str
    artifact: str = field(repr=False)
    claim_token: str = field(repr=False)
    lease_expires_at: str


def _required(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MailArtifactBrokerError(f"{name} is required")
    return text


def _service_material(
    *,
    action: str,
    timestamp_value: str,
    request_id: str,
    application_key: str,
) -> bytes:
    return "\n".join(
        ("v1", action, timestamp_value, request_id, application_key)
    ).encode("utf-8")


class MailArtifactBrokerClient:
    """Privileged, in-memory-only client for Hunter's one-time mail broker.

    The returned verification artifact and claim token must stay in process memory.
    This client does not write them to SQLite, logs, receipts, Teach recipes, or
    application state and has no application-submit authority.
    """

    def __init__(
        self,
        *,
        base_url: str,
        hmac_secret: str,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        normalized_url = _required(base_url, "base_url").rstrip("/")
        parsed = urlparse(normalized_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise MailArtifactBrokerError(
                "Mail artifact broker requires an HTTPS endpoint"
            )
        secret = hmac_secret.encode("utf-8")
        if len(secret) < 32:
            raise MailArtifactBrokerError(
                "Mail artifact broker HMAC secret must be at least 32 bytes"
            )
        self.base_url = normalized_url
        self._secret = secret
        self._client = client or httpx.Client(timeout=10.0)
        self._clock = clock

    def _headers(
        self,
        *,
        action: str,
        request_id: str,
        application_key: str,
    ) -> dict[str, str]:
        timestamp_value = str(int(self._clock()))
        digest = hmac.new(
            self._secret,
            _service_material(
                action=action,
                timestamp_value=timestamp_value,
                request_id=request_id,
                application_key=application_key,
            ),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Munshi-Timestamp": timestamp_value,
            "X-Munshi-Signature": f"sha256={digest}",
            "Content-Type": "application/json",
        }

    def _post(
        self,
        *,
        path: str,
        action: str,
        request_id: str,
        application_key: str,
        payload: dict[str, str],
    ) -> dict[str, object]:
        headers = self._headers(
            action=action,
            request_id=request_id,
            application_key=application_key,
        )
        try:
            response = self._client.post(
                f"{self.base_url}{path}",
                headers=headers,
                json=payload,
            )
        except httpx.HTTPError as error:
            raise MailArtifactBrokerError(
                "Mail artifact broker request failed safely"
            ) from error
        if response.status_code != 200:
            raise MailArtifactBrokerError(
                f"Mail artifact broker rejected {action} with HTTP "
                f"{response.status_code}"
            )
        try:
            decoded = response.json()
        except ValueError as error:
            raise MailArtifactBrokerError(
                "Mail artifact broker returned invalid JSON"
            ) from error
        if not isinstance(decoded, dict) or decoded.get("success") is not True:
            raise MailArtifactBrokerError(
                "Mail artifact broker response is not successful"
            )
        return decoded

    def claim(
        self,
        *,
        request_id: str,
        application_key: str,
    ) -> ClaimedMailArtifact:
        request_id = _required(request_id, "request_id")
        application_key = _required(application_key, "application_key")
        decoded = self._post(
            path="/api/mail/artifacts/claim",
            action="claim",
            request_id=request_id,
            application_key=application_key,
            payload={
                "request_id": request_id,
                "application_key": application_key,
            },
        )
        response_request_id = _required(decoded.get("request_id"), "request_id")
        if response_request_id != request_id:
            raise MailArtifactBrokerError(
                "Mail artifact broker changed the verification request binding"
            )
        artifact_kind = _required(decoded.get("artifact_kind"), "artifact_kind").upper()
        if artifact_kind not in _ALLOWED_ARTIFACT_KINDS:
            raise MailArtifactBrokerError(
                "Mail artifact broker returned an unsupported artifact kind"
            )
        artifact = _required(decoded.get("artifact"), "artifact")
        artifact_digest = _required(
            decoded.get("artifact_digest"),
            "artifact_digest",
        ).lower()
        expected_digest = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(artifact_digest, expected_digest):
            raise MailArtifactBrokerError(
                "Mail artifact broker payload failed digest verification"
            )
        claim_token = _required(decoded.get("claim_token"), "claim_token")
        lease_expires_at = _required(
            decoded.get("lease_expires_at"),
            "lease_expires_at",
        )
        return ClaimedMailArtifact(
            request_id=request_id,
            artifact_kind=artifact_kind,
            artifact_digest=artifact_digest,
            artifact=artifact,
            claim_token=claim_token,
            lease_expires_at=lease_expires_at,
        )

    def consume(
        self,
        *,
        request_id: str,
        application_key: str,
        claim_token: str,
    ) -> None:
        request_id = _required(request_id, "request_id")
        application_key = _required(application_key, "application_key")
        claim_token = _required(claim_token, "claim_token")
        decoded = self._post(
            path="/api/mail/artifacts/consume",
            action="consume",
            request_id=request_id,
            application_key=application_key,
            payload={
                "request_id": request_id,
                "application_key": application_key,
                "claim_token": claim_token,
            },
        )
        if _required(decoded.get("request_id"), "request_id") != request_id:
            raise MailArtifactBrokerError(
                "Mail artifact broker changed the consume request binding"
            )
        if str(decoded.get("state") or "").upper() != "CONSUMED":
            raise MailArtifactBrokerError(
                "Mail artifact broker did not confirm one-time consumption"
            )
        if decoded.get("artifact_retained") is not False:
            raise MailArtifactBrokerError(
                "Mail artifact broker did not confirm artifact destruction"
            )
