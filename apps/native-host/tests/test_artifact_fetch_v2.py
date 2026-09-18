from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from munshi_apply_native import artifact_fetch_v2 as module
from munshi_apply_native.artifact_fetch_v2 import HunterExecutionBridgeClient

SECRET = "-".join(("phase1cb", "client", "test", "secret"))
ARTIFACT = b"%PDF-1.4\n% client fixture\n%%EOF\n"
ARTIFACT_SHA = hashlib.sha256(ARTIFACT).hexdigest()


def _plan():
    return {
        "application_id": "application-1",
        "plan_id": "plan-1",
        "plan_digest": "a" * 64,
        "resume": {
            "artifact_id": "artifact-1",
            "artifact_reference": "hunter-native-resume://resume-1/pdf",
            "artifact_sha256": ARTIFACT_SHA,
        },
    }


def _signed_response(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    purpose = payload["purpose"]
    if purpose == module.PURPOSE_PLAN_CURRENT:
        body = json.dumps(
            {
                "version": module.RESPONSE_VERSION,
                "request_id": payload["request_id"],
                "purpose": purpose,
                "plan_id": payload["plan_id"],
                "plan_digest": payload["plan_digest"],
                "fresh": True,
                "submission_authority": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        headers = {}
    elif purpose == module.PURPOSE_AUTOAPPLY_CONFIG:
        body = json.dumps(
            {
                "version": module.RESPONSE_VERSION,
                "request_id": payload["request_id"],
                "purpose": purpose,
                "plan_id": payload["plan_id"],
                "plan_digest": payload["plan_digest"],
                "config": {
                    "enabled": True,
                    "authMode": "api",
                    "model": "sonnet",
                    "headless": True,
                    "maxTurns": 40,
                    "maxCostPerApplicationUsd": 1.0,
                    "allowFinalSubmit": False,
                    "challengeServiceEnabled": False,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        headers = {}
    elif purpose == module.PURPOSE_AUTOAPPLY_ANTHROPIC_SECRET:
        body = b"dashboard-anthropic-secret"
        headers = {
            "X-Munshi-Credential-Type": "autoapply_anthropic_api_key",
            "X-Munshi-Submission-Authority": "false",
        }
    else:
        body = ARTIFACT
        headers = {
            "X-Munshi-Artifact-SHA256": ARTIFACT_SHA,
            "X-Munshi-Submission-Authority": "false",
        }
    digest = hashlib.sha256(body).hexdigest()
    signature = hmac.new(
        SECRET.encode(),
        f"{payload['request_id']}.{purpose}.{digest}.{payload['plan_digest']}".encode(),
        hashlib.sha256,
    ).hexdigest()
    headers.update(
        {
            "X-Munshi-Response-Event-Id": payload["request_id"],
            "X-Munshi-Response-Purpose": purpose,
            "X-Munshi-Response-SHA256": digest,
            "X-Munshi-Plan-Digest": payload["plan_digest"],
            "X-Munshi-Response-Signature": f"sha256={signature}",
        }
    )
    return httpx.Response(200, content=body, headers=headers)


def test_current_plan_and_artifact_are_response_signed(monkeypatch):
    monkeypatch.setattr(module.time, "time", lambda: 1000)
    client = HunterExecutionBridgeClient(
        base_url="https://hunter.internal",
        secret=SECRET,
        tenant_id="tenant-a",
        user_id="member-a",
        transport=httpx.MockTransport(_signed_response),
    )
    assert client.plan_is_current(_plan()) is True
    assert client.artifact_bytes(_plan()) == ARTIFACT
    client.close()


def test_dashboard_autoapply_config_and_secret_are_response_signed(monkeypatch):
    monkeypatch.setattr(module.time, "time", lambda: 1000)
    client = HunterExecutionBridgeClient(
        base_url="https://hunter.internal",
        secret=SECRET,
        tenant_id="tenant-a",
        user_id="member-a",
        transport=httpx.MockTransport(_signed_response),
    )

    config = client.autoapply_config(_plan())
    assert config["enabled"] is True
    assert config["authMode"] == "api"
    assert config["model"] == "sonnet"
    assert client.anthropic_api_key(_plan()) == "dashboard-anthropic-secret"
    client.close()


def test_tampered_response_fails_closed(monkeypatch):
    monkeypatch.setattr(module.time, "time", lambda: 1000)

    def tampered(request):
        response = _signed_response(request)
        return httpx.Response(200, content=response.content + b"x", headers=response.headers)

    client = HunterExecutionBridgeClient(
        base_url="https://hunter.internal",
        secret=SECRET,
        tenant_id="tenant-a",
        user_id="member-a",
        transport=httpx.MockTransport(tampered),
    )
    assert client.plan_is_current(_plan()) is False
    try:
        client.artifact_bytes(_plan())
    except RuntimeError as error:
        assert "digest" in str(error)
    else:
        raise AssertionError("Tampered artifact response was accepted")
    client.close()


def test_plain_http_requires_exact_configured_internal_target(monkeypatch: pytest.MonkeyPatch):
    target = "http://hunter-target.internal:8123"
    with pytest.raises(ValueError, match="HTTPS"):
        HunterExecutionBridgeClient(
            base_url=target, secret=SECRET, tenant_id="tenant-a", user_id="member-a"
        )

    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "integration")
    monkeypatch.setenv("MUNSHI_HUNTER_INTERNAL_HTTP_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_HUNTER_INTERNAL_HTTP_BASE_URL", target)
    HunterExecutionBridgeClient(
        base_url=target,
        secret=SECRET,
        tenant_id="tenant-a",
        user_id="member-a",
    ).close()

    with pytest.raises(ValueError, match="HTTPS"):
        HunterExecutionBridgeClient(
            base_url="http://different-target.internal:8123",
            secret=SECRET,
            tenant_id="tenant-a",
            user_id="member-a",
        )
    with pytest.raises(ValueError, match="HTTPS"):
        HunterExecutionBridgeClient(
            base_url=target + "/other",
            secret=SECRET,
            tenant_id="tenant-a",
            user_id="member-a",
        )

    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="HTTPS"):
        HunterExecutionBridgeClient(
            base_url=target,
            secret=SECRET,
            tenant_id="tenant-a",
            user_id="member-a",
        )
