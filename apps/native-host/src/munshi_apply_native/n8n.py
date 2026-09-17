from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from . import __version__


@dataclass(frozen=True)
class SignedWebhook:
    body: bytes
    headers: dict[str, str]


def sign_event(
    event: dict[str, Any],
    secret: str,
    *,
    timestamp: int | None = None,
) -> SignedWebhook:
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("Canonical event_id is required for n8n delivery")
    body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body_hash = hashlib.sha256(body).hexdigest()
    created_at = str(int(time.time()) if timestamp is None else timestamp)
    signed_content = f"{event_id}.{created_at}.{body_hash}".encode()
    signature = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return SignedWebhook(
        body=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"MUNSHI-Apply/{__version__}",
            "X-Munshi-Event-Id": event_id,
            "X-Munshi-Timestamp": created_at,
            "X-Munshi-Content-SHA256": body_hash,
            "X-Munshi-Signature": f"sha256={signature}",
        },
    )


def verify_signature(
    *,
    event_id: str,
    timestamp: str,
    body: bytes,
    content_sha256: str,
    signature: str,
    secret: str,
    now: int | None = None,
    max_age_seconds: int = 300,
) -> bool:
    try:
        signed_at = int(timestamp)
    except ValueError:
        return False
    current_time = int(time.time()) if now is None else now
    if abs(current_time - signed_at) > max_age_seconds:
        return False
    actual_hash = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(actual_hash, content_sha256):
        return False
    signed_content = f"{event_id}.{timestamp}.{actual_hash}".encode()
    expected = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def forward_event(
    url: str,
    event: dict[str, Any],
    secret: str,
    timeout_seconds: float = 5.0,
) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("n8n webhook must be an absolute HTTP or HTTPS URL")
    signed = sign_event(event, secret)
    request = urllib.request.Request(  # noqa: S310 - URL scheme validated above.
        url,
        data=signed.body,
        headers=signed.headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        if not 200 <= response.status < 300:
            raise RuntimeError(f"n8n webhook returned HTTP {response.status}")
