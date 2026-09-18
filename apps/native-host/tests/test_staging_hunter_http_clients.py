from __future__ import annotations

import pytest

from munshi_apply_native.hunter_submit_authority_client_v1 import (
    HunterSubmitAuthorityClient,
    SubmitAuthorizationClientError,
)
from munshi_apply_native.production_receipt_v1 import (
    ProductionReceiptClient,
    ProductionReceiptError,
)

SECRET = "staging-only-test-secret-0123456789abcdef"  # noqa: S105


def _enable_internal_staging_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "staging")
    monkeypatch.setenv("MUNSHI_HUNTER_EXECUTION_BRIDGE_STAGING_HTTP_ENABLED", "true")


def test_submit_authority_client_allows_exact_internal_staging_hunter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_internal_staging_http(monkeypatch)
    client = HunterSubmitAuthorityClient(
        base_url="http://hunter:8000",
        secret=SECRET,
    )
    assert client.base_url == "http://hunter:8000"


def test_receipt_client_allows_exact_internal_staging_hunter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_internal_staging_http(monkeypatch)
    client = ProductionReceiptClient(
        base_url="http://hunter:8000",
        secret=SECRET,
    )
    assert client.base_url == "http://hunter:8000"


@pytest.mark.parametrize(
    ("client_cls", "error_cls"),
    [
        (HunterSubmitAuthorityClient, SubmitAuthorizationClientError),
        (ProductionReceiptClient, ProductionReceiptError),
    ],
)
def test_internal_hunter_http_remains_blocked_outside_staging(
    monkeypatch: pytest.MonkeyPatch,
    client_cls: type[object],
    error_cls: type[Exception],
) -> None:
    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "production")
    monkeypatch.setenv("MUNSHI_HUNTER_EXECUTION_BRIDGE_STAGING_HTTP_ENABLED", "true")
    with pytest.raises(error_cls):
        client_cls(base_url="http://hunter:8000", secret=SECRET)


@pytest.mark.parametrize(
    ("client_cls", "error_cls"),
    [
        (HunterSubmitAuthorityClient, SubmitAuthorizationClientError),
        (ProductionReceiptClient, ProductionReceiptError),
    ],
)
def test_staging_http_does_not_allow_arbitrary_hosts(
    monkeypatch: pytest.MonkeyPatch,
    client_cls: type[object],
    error_cls: type[Exception],
) -> None:
    _enable_internal_staging_http(monkeypatch)
    with pytest.raises(error_cls):
        client_cls(base_url="http://example.invalid:8000", secret=SECRET)
