from __future__ import annotations

import httpx
import pytest

from munshi_apply_native.hunter_submit_authority_client_v1 import (
    HunterSubmitAuthorityClient,
    SubmitAuthorizationClientError,
)
from munshi_apply_native.mail_artifact_broker import (
    MailArtifactBrokerClient,
    MailArtifactBrokerError,
)
from munshi_apply_native.production_receipt_v1 import (
    ProductionReceiptClient,
    ProductionReceiptError,
)

TEST_HMAC_KEY_MATERIAL = "target-http-test-material-0123456789abcdef"
TARGET_URL = "http://hunter-target.internal:8123"


def _enable_internal_target_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "integration")
    monkeypatch.setenv("MUNSHI_HUNTER_INTERNAL_HTTP_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_HUNTER_INTERNAL_HTTP_BASE_URL", TARGET_URL)


@pytest.mark.parametrize(
    ("client_cls", "error_cls"),
    [
        (HunterSubmitAuthorityClient, SubmitAuthorizationClientError),
        (ProductionReceiptClient, ProductionReceiptError),
    ],
)
def test_control_clients_allow_exact_configured_internal_target(
    monkeypatch: pytest.MonkeyPatch,
    client_cls: type[object],
    error_cls: type[Exception],
) -> None:
    del error_cls
    _enable_internal_target_http(monkeypatch)
    client = client_cls(base_url=TARGET_URL, secret=TEST_HMAC_KEY_MATERIAL)
    assert client.base_url == TARGET_URL


@pytest.mark.parametrize(
    ("client_cls", "error_cls"),
    [
        (HunterSubmitAuthorityClient, SubmitAuthorizationClientError),
        (ProductionReceiptClient, ProductionReceiptError),
    ],
)
def test_internal_http_remains_blocked_in_production(
    monkeypatch: pytest.MonkeyPatch,
    client_cls: type[object],
    error_cls: type[Exception],
) -> None:
    _enable_internal_target_http(monkeypatch)
    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "production")
    with pytest.raises(error_cls):
        client_cls(base_url=TARGET_URL, secret=TEST_HMAC_KEY_MATERIAL)


@pytest.mark.parametrize(
    ("client_cls", "error_cls"),
    [
        (HunterSubmitAuthorityClient, SubmitAuthorizationClientError),
        (ProductionReceiptClient, ProductionReceiptError),
    ],
)
def test_internal_http_does_not_allow_url_other_than_configured_target(
    monkeypatch: pytest.MonkeyPatch,
    client_cls: type[object],
    error_cls: type[Exception],
) -> None:
    _enable_internal_target_http(monkeypatch)
    with pytest.raises(error_cls):
        client_cls(
            base_url="http://different-target.internal:8123",
            secret=TEST_HMAC_KEY_MATERIAL,
        )


def test_mail_artifact_broker_allows_exact_configured_internal_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_internal_target_http(monkeypatch)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(500, json={"success": False})
    )
    client = httpx.Client(transport=transport)
    try:
        broker = MailArtifactBrokerClient(
            base_url=TARGET_URL,
            hmac_secret=TEST_HMAC_KEY_MATERIAL,
            client=client,
        )
        assert broker.base_url == TARGET_URL
    finally:
        client.close()


def test_mail_artifact_broker_blocks_internal_http_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_internal_target_http(monkeypatch)
    monkeypatch.setenv("MUNSHI_ENVIRONMENT", "prod")
    with pytest.raises(MailArtifactBrokerError):
        MailArtifactBrokerClient(
            base_url=TARGET_URL,
            hmac_secret=TEST_HMAC_KEY_MATERIAL,
        )


def test_mail_artifact_broker_blocks_nonconfigured_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_internal_target_http(monkeypatch)
    with pytest.raises(MailArtifactBrokerError):
        MailArtifactBrokerClient(
            base_url="http://different-target.internal:8123",
            hmac_secret=TEST_HMAC_KEY_MATERIAL,
        )
