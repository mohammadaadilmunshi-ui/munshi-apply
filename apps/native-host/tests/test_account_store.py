from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.account_store import AccountStore, portal_identity
from munshi_apply_native.application_store import ApplicationStore
from munshi_apply_native.database import Database


NOW = "2026-08-17T19:00:00+00:00"


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "accounts.sqlite", migrations)
    result.migrate()
    return result


def test_account_upsert_lookup_and_idempotent_link(tmp_path: Path) -> None:
    db = database(tmp_path)
    ApplicationStore(db).ensure("application-1", NOW)
    store = AccountStore(db)

    first = store.upsert(
        {
            "accountId": "account-1",
            "employer": "Example",
            "portalUrl": "https://example.com/candidate/login?return=/apply",
            "email": "AADIL@EXAMPLE.COM",
            "exists": True,
            "applicationId": "application-1",
            "observedAt": NOW,
        }
    )
    second = store.upsert(
        {
            "accountId": "ignored-new-id",
            "employer": "Example Company",
            "portalUrl": "https://example.com/candidate/login",
            "email": "aadil@example.com",
            "exists": True,
            "applicationId": "application-1",
            "observedAt": "2026-08-17T19:05:00+00:00",
        }
    )

    assert first["accountId"] == "account-1"
    assert first["portalUrl"] == "https://example.com/candidate/login"
    assert first["applicationIds"] == ["application-1"]
    assert second["accountId"] == "account-1"
    assert second["employer"] == "Example Company"
    assert second["applicationIds"] == ["application-1"]
    assert store.lookup(
        {
            "portalUrl": "https://example.com/candidate/login",
            "email": "aadil@example.com",
        }
    ) == [second]


def test_account_registry_has_no_secret_columns_and_rejects_secret_payloads(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    with db.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(account_records)").fetchall()
        }
    assert not {
        "password",
        "secret",
        "token",
        "credential",
        "otp",
    }.intersection(columns)

    with pytest.raises(ValueError, match="refuses passwords"):
        AccountStore(db).upsert(
            {
                "portalUrl": "https://example.com/login",
                "email": "aadil@example.com",
                "password": "never-store-this",
                "observedAt": NOW,
            }
        )


def test_workday_tenant_scope_isolated(tmp_path: Path) -> None:
    db = database(tmp_path)
    store = AccountStore(db)
    first = "https://wd5.myworkdayjobs.com/CompanyOne/job/New-York/Role_123"
    second = "https://wd5.myworkdayjobs.com/CompanyTwo/job/New-York/Role_456"

    assert portal_identity(first)[1] == "wd5.myworkdayjobs.com/companyone"
    assert portal_identity(second)[1] == "wd5.myworkdayjobs.com/companytwo"

    store.upsert(
        {
            "accountId": "account-one",
            "employer": "Company One",
            "portalUrl": first,
            "email": "aadil@example.com",
            "observedAt": NOW,
        }
    )
    assert len(store.lookup({"portalUrl": first})) == 1
    assert store.lookup({"portalUrl": second}) == []


def test_embedded_credentials_in_portal_url_are_rejected(tmp_path: Path) -> None:
    db = database(tmp_path)
    with pytest.raises(ValueError, match="embedded credentials"):
        AccountStore(db).lookup(
            {"portalUrl": "https://user:password@example.com/candidate/login"}
        )
