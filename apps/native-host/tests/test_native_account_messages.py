from __future__ import annotations

from pathlib import Path

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


def test_native_health_advertises_account_orchestration(tmp_path: Path) -> None:
    response = handle({"type": "PING"}, database(tmp_path))
    assert response["ok"] is True
    assert response["data"]["capabilities"]["account_orchestration"] is True
