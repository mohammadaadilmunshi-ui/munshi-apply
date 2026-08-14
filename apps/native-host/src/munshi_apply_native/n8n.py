from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request
from typing import Any
from urllib.parse import urlparse


def forward_event(
    url: str,
    event: dict[str, Any],
    secret: str | None = None,
    timeout_seconds: float = 5.0,
) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("n8n webhook must be an absolute HTTP or HTTPS URL")
    body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "MUNSHI-Apply/0.1"}
    if secret:
        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest()
        headers["X-Munshi-Timestamp"] = timestamp
        headers["X-Munshi-Signature"] = f"sha256={signature}"
    request = urllib.request.Request(  # noqa: S310 - URL scheme validated above.
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        if not 200 <= response.status < 300:
            raise RuntimeError(f"n8n webhook returned HTTP {response.status}")
