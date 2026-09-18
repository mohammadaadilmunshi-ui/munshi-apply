from __future__ import annotations

from munshi_apply_native import internal_http_policy as policy


def test_production_internal_hunter_http_is_default_denied(monkeypatch):
    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "production")
    monkeypatch.setenv("MUNSHI_HUNTER_INTERNAL_HTTP_BASE_URL", "http://hunter:8000")
    monkeypatch.delenv("MUNSHI_PRODUCTION_INTERNAL_BRIDGE_ENABLED", raising=False)
    assert policy.internal_hunter_http_allowed("http://hunter:8000") is False


def test_production_internal_hunter_http_requires_exact_private_target(monkeypatch):
    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "production")
    monkeypatch.setenv("MUNSHI_PRODUCTION_INTERNAL_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_HUNTER_INTERNAL_HTTP_BASE_URL", "http://hunter:8000")
    assert policy.internal_hunter_http_allowed("http://hunter:8000") is True
    assert policy.internal_hunter_http_allowed("http://other:8000") is False
    assert policy.internal_hunter_http_allowed("http://hunter.example.com:8000") is False
