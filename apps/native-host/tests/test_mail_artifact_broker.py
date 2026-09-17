from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from munshi_apply_native.mail_artifact_broker import (
    MailArtifactBrokerClient,
    MailArtifactBrokerError,
)

SECRET = "m" * 32
REQUEST_ID = "verification-request-1"
APPLICATION_KEY = "application-key-1"
TIMESTAMP = "1789588800"
CLAIM_TOKEN = hashlib.sha256(b"mail-broker-test-claim-token").hexdigest()


def _expected_signature(action: str) -> str:
    material = "\n".join(
        ("v1", action, TIMESTAMP, REQUEST_ID, APPLICATION_KEY)
    ).encode("utf-8")
    digest = hmac.new(SECRET.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_claim_and_consume_match_hunter_contract_without_repr_secret_leak() -> None:
    artifact = "482915"
    artifact_digest = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert request.headers["X-Munshi-Timestamp"] == TIMESTAMP
        assert body["request_id"] == REQUEST_ID
        assert body["application_key"] == APPLICATION_KEY
        if request.url.path.endswith("/claim"):
            calls.append("claim")
            assert request.headers["X-Munshi-Signature"] == _expected_signature(
                "claim"
            )
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "request_id": REQUEST_ID,
                    "artifact_kind": "EMAIL_VERIFICATION_CODE",
                    "artifact_digest": artifact_digest,
                    "artifact": artifact,
                    "claim_token": CLAIM_TOKEN,
                    "lease_expires_at": "2026-09-16T21:30:00+00:00",
                },
            )
        calls.append("consume")
        assert request.headers["X-Munshi-Signature"] == _expected_signature(
            "consume"
        )
        assert body["claim_token"] == CLAIM_TOKEN
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": REQUEST_ID,
                "state": "CONSUMED",
                "artifact_retained": False,
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        broker = MailArtifactBrokerClient(
            base_url="https://hunter.test",
            hmac_secret=SECRET,
            client=http_client,
            clock=lambda: float(TIMESTAMP),
        )
        claimed = broker.claim(
            request_id=REQUEST_ID,
            application_key=APPLICATION_KEY,
        )
        assert claimed.artifact == artifact
        assert claimed.artifact_digest == artifact_digest
        assert artifact not in repr(claimed)
        assert CLAIM_TOKEN not in repr(claimed)
        broker.consume(
            request_id=REQUEST_ID,
            application_key=APPLICATION_KEY,
            claim_token=claimed.claim_token,
        )

    assert calls == ["claim", "consume"]


def test_claim_rejects_tampered_artifact_digest() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": REQUEST_ID,
                "artifact_kind": "MAGIC_LOGIN_LINK",
                "artifact_digest": "0" * 64,
                "artifact": "https://ats.example.test/magic/opaque",
                "claim_token": CLAIM_TOKEN,
                "lease_expires_at": "2026-09-16T21:30:00+00:00",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        broker = MailArtifactBrokerClient(
            base_url="https://hunter.test",
            hmac_secret=SECRET,
            client=http_client,
            clock=lambda: float(TIMESTAMP),
        )
        with pytest.raises(MailArtifactBrokerError, match="digest"):
            broker.claim(
                request_id=REQUEST_ID,
                application_key=APPLICATION_KEY,
            )


def test_broker_requires_https_and_strong_service_secret() -> None:
    with pytest.raises(MailArtifactBrokerError, match="HTTPS"):
        MailArtifactBrokerClient(
            base_url="http://hunter.test",
            hmac_secret=SECRET,
        )
    short_secret = "".join(("sho", "rt"))
    with pytest.raises(MailArtifactBrokerError, match="32 bytes"):
        MailArtifactBrokerClient(
            base_url="https://hunter.test",
            hmac_secret=short_secret,
        )
