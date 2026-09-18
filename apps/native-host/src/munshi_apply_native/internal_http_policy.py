from __future__ import annotations

import os
from urllib.parse import urlparse


def _truthy(name: str) -> bool:
    return str(os.getenv(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def internal_hunter_http_allowed(base_url: str) -> bool:
    """Allow one explicitly configured internal HTTP Hunter endpoint outside production."""
    normalized = str(base_url or "").strip().rstrip("/")
    environment = str(os.getenv("MUNSHI_ENVIRONMENT") or "").strip().casefold()
    if environment in {"prod", "production"}:
        return False
    if not _truthy("MUNSHI_HUNTER_INTERNAL_HTTP_ENABLED"):
        return False

    allowed = str(os.getenv("MUNSHI_HUNTER_INTERNAL_HTTP_BASE_URL") or "").strip().rstrip("/")
    if not allowed or normalized != allowed:
        return False

    parsed = urlparse(normalized)
    return bool(
        parsed.scheme == "http"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )
