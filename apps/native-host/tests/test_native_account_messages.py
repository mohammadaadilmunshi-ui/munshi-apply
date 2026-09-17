from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle

NOW = "2026-08-17T19:00:00+00:00"


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "native-accounts.sqlite", migrations)
    result.migrate()
    return result


def test_native_account_upsert_and_lookup_round_trip(tmp_path: Path) -> None:
    db = database(tmp_path)
    saved = handle(
        {
            "type": "UPSERT_ACCOUNT",
            "payload": {
                "accountId": "account-native",
                "employer": "Example",
                "portalUrl": "https://example.com/candidate/login",
                "email": "aadil@example.com",
                "exists": True,
                "applicationId": "application-native",
                "observedAt": NOW,
            },
        },
        db,
    )
    assert saved["ok"] is True
    assert saved["data"]["accountId"] == "account-native"
    assert saved["data"]["applicationIds"] == ["application-native"]

    lookup = handle(
        {
            "type": "LOOKUP_ACCOUNTS",
            "payload": {
                "portalUrl": "https://example.com/candidate/login",
                "email": "aadil@example.com",
            },
        },
        db,
    )
    assert lookup == {"ok": True, "data": [saved["data"]]}


def test_native_account_lifecycle_accepts_hunter_opaque_secret_ref(tmp_path: Path) -> None:
    db = database(tmp_path)
    handle(
        {
            "type": "UPSERT_ACCOUNT",
            "payload": {
                "accountId": "account-hunter-ref",
                "employer": "Example",
                "portalUrl": "https://example.com/candidate/login",
                "email": "u_abcdefghijklmnop@mail.munshi.systems",
                "exists": False,
                "applicationId": "application-hunter-ref",
                "observedAt": NOW,
            },
        },
        db,
    )
    provisioned = handle(
        {
            "type": "PROVISION_ATS_ACCOUNT",
            "payload": {
                "accountId": "account-hunter-ref",
                "provider": "workday",
                "credentialRef": "ats-secret://account-hunter-ref/password",
                "mailAlias": "u_abcdefghijklmnop@mail.munshi.systems",
                "observedAt": NOW,
            },
        },
        db,
    )
    assert provisioned["ok"] is True
    assert (
        provisioned["data"]["credential_ref"]
        == "ats-secret://account-hunter-ref/password"
    )


def test_native_verification_ready_rejects_raw_link_or_code_material(tmp_path: Path) -> None:
    db = database(tmp_path)
    handle(
        {
            "type": "UPSERT_ACCOUNT",
            "payload": {
                "accountId": "account-verify-boundary",
                "employer": "Example",
                "portalUrl": "https://example.com/candidate/login",
                "email": "u_abcdefghijklmnop@mail.munshi.systems",
                "exists": False,
                "applicationId": "application-verify-boundary",
                "observedAt": NOW,
            },
        },
        db,
    )
    handle(
        {
            "type": "PROVISION_ATS_ACCOUNT",
            "payload": {
                "accountId": "account-verify-boundary",
                "provider": "workday",
                "mailAlias": "u_abcdefghijklmnop@mail.munshi.systems",
                "observedAt": NOW,
            },
        },
        db,
    )
    handle(
        {
            "type": "BIND_ATS_ACCOUNT_CONTINUATION",
            "payload": {
                "continuationId": "continuation-verify-boundary",
                "accountId": "account-verify-boundary",
                "applicationId": "application-verify-boundary",
                "executionSessionId": "session-verify-boundary",
                "provider": "workday",
                "targetFingerprint": "target-verify-boundary",
                "observedAt": NOW,
            },
        },
        db,
    )
    handle(
        {
            "type": "START_ATS_EMAIL_VERIFICATION",
            "payload": {
                "challengeId": "challenge-verify-boundary",
                "accountId": "account-verify-boundary",
                "applicationId": "application-verify-boundary",
                "continuationId": "continuation-verify-boundary",
                "kind": "EMAIL_LINK",
                "observedAt": NOW,
            },
        },
        db,
    )

    with pytest.raises(ValueError, match="forbidden value-bearing fields"):
        handle(
            {
                "type": "MARK_ATS_EMAIL_VERIFICATION_READY",
                "payload": {
                    "challengeId": "challenge-verify-boundary",
                    "mailEventId": "mail-event-verify-boundary",
                    "artifactDigest": "a" * 64,
                    "verificationUrl": "https://example.test/verify?token=raw",
                    "observedAt": NOW,
                },
            },
            db,
        )


def test_native_health_advertises_account_orchestration(tmp_path: Path) -> None:
    response = handle({"type": "PING"}, database(tmp_path))
    assert response["ok"] is True
    assert response["data"]["capabilities"]["account_orchestration"] is True
