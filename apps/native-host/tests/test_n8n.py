from __future__ import annotations

import hashlib
import hmac
from unittest.mock import MagicMock, patch

from munshi_apply_native.n8n import forward_event


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
            {"eventId": "evt-1"},
            "test-secret",
        )

    request = opened.call_args.args[0]
    body = b'{"eventId":"evt-1"}'
    expected = hmac.new(
        b"test-secret", b"1765000000." + body, hashlib.sha256
    ).hexdigest()
    assert request.get_header("X-munshi-timestamp") == "1765000000"
    assert request.get_header("X-munshi-signature") == f"sha256={expected}"


def test_n8n_rejects_non_http_urls() -> None:
    try:
        forward_event("file:///tmp/webhook", {"eventId": "evt-1"})
    except ValueError as error:
        assert "HTTP or HTTPS" in str(error)
    else:
        raise AssertionError("Unsafe webhook URL was accepted")
