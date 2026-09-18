from __future__ import annotations

import os
from urllib.parse import urlparse


def _truthy(name: str) -> bool:
    return str(os.getenv(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def internal_hunter_http_allowed(base_url: str) -> bool:
    """Allow one exact private Docker-bridge Hunter endpoint.

    Production remains default-deny. It may opt in only with the dedicated
    production bridge gate and an exact single-label Docker DNS target. All
    application-execution traffic remains HMAC authenticated independently.
    """
    normalized = str(base_url or "").strip().rstrip("/")
    environment = str(os.getenv("MUNSHI_ENVIRONMENT") or "").strip().casefold()
    production = environment in {"prod", "production"}
    if production:
        if not _truthy("MUNSHI_PRODUCTION_INTERNAL_BRIDGE_ENABLED"):
            return False
    elif not _truthy("MUNSHI_HUNTER_INTERNAL_HTTP_ENABLED"):
        return False

    allowed = str(os.getenv("MUNSHI_HUNTER_INTERNAL_HTTP_BASE_URL") or "").strip().rstrip("/")
    if not allowed or normalized != allowed:
        return False

    parsed = urlparse(normalized)
    host = str(parsed.hostname or "")
    return bool(
        parsed.scheme == "http"
        and host
        and "." not in host
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )
