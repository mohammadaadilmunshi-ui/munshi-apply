from __future__ import annotations

import hashlib
import hmac
from unittest.mock import MagicMock, patch

from munshi_apply_native.n8n import forward_event, sign_event, verify_signature


def canonical_event() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": "evt-1",
        "correlation_id": "correlation-1",
        "event_type": "PAGE_DETECTED",
        "occurred_at": "2026-08-14T12:00:00+00:00",
        "application_id": None,
        "source": "munshi-apply",
        "payload": {"controls": 2},
    }


def test_n8n_request_is_signed_when_secret_is_configured() -> None:
    response = MagicMock()
    response.status = 202
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False

    with (
        patch("munshi_apply_native.n8n.time.time", return_value=1_765_000_000),
        patch("munshi_apply_native.n8n.urllib.request.urlopen", return_value=context) as opened,
    ):
        forward_event(
            "https://n8n.example.test/webhook/munshi",
            canonical_event(),
            "test-secret",
        )

    request = opened.call_args.args[0]
    body = request.data
    body_hash = hashlib.sha256(body).hexdigest()
    expected = hmac.new(
        b"test-secret",
        f"evt-1.1765000000.{body_hash}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert request.get_header("X-munshi-event-id") == "evt-1"
    assert request.get_header("X-munshi-timestamp") == "1765000000"
    assert request.get_header("X-munshi-content-sha256") == body_hash
    assert request.get_header("X-munshi-signature") == f"sha256={expected}"


def test_n8n_rejects_non_http_urls() -> None:
    try:
        forward_event("file:///tmp/webhook", canonical_event(), "test-secret")
    except ValueError as error:
        assert "HTTP or HTTPS" in str(error)
    else:
        raise AssertionError("Unsafe webhook URL was accepted")


def test_signature_verification_rejects_expired_or_tampered_content() -> None:
    signing_key = "test-secret"
    signed = sign_event(canonical_event(), signing_key, timestamp=1_765_000_000)
    headers = signed.headers

    assert verify_signature(
        event_id=headers["X-Munshi-Event-Id"],
        timestamp=headers["X-Munshi-Timestamp"],
        body=signed.body,
        content_sha256=headers["X-Munshi-Content-SHA256"],
        signature=headers["X-Munshi-Signature"],
        secret=signing_key,
        now=1_765_000_100,
    )
    assert not verify_signature(
        event_id=headers["X-Munshi-Event-Id"],
        timestamp=headers["X-Munshi-Timestamp"],
        body=signed.body,
        content_sha256=headers["X-Munshi-Content-SHA256"],
        signature=headers["X-Munshi-Signature"],
        secret=signing_key,
        now=1_765_000_301,
    )
    assert not verify_signature(
        event_id=headers["X-Munshi-Event-Id"],
        timestamp=headers["X-Munshi-Timestamp"],
        body=signed.body + b" ",
        content_sha256=headers["X-Munshi-Content-SHA256"],
        signature=headers["X-Munshi-Signature"],
        secret=signing_key,
        now=1_765_000_100,
    )
