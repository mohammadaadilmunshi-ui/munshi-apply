from __future__ import annotations

from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.hosted_account_session import HostedAccountSessionStore


def _database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "session.sqlite", migrations)
    database.migrate()
    return database


def test_chromium_storage_state_is_encrypted_and_round_trips(tmp_path: Path) -> None:
    database = _database(tmp_path)
    store = HostedAccountSessionStore(database, bridge_secret=b"h" * 32)
    state = {
        "cookies": [
            {
                "name": "session",
                "value": "super-secret-cookie-value",
                "domain": "example.com",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ],
        "origins": [],
    }
    store.save(
        tenant_id="tenant-1",
        user_id="user-1",
        scope_key="example.com",
        account_id="account-1",
        storage_state=state,
    )

    with database.connect() as connection:
        row = connection.execute(
            "SELECT ciphertext,nonce,state_sha256 FROM hosted_account_sessions"
        ).fetchone()
    assert row is not None
    assert b"super-secret-cookie-value" not in bytes(row["ciphertext"])
    assert len(bytes(row["nonce"])) == 12
    assert len(str(row["state_sha256"])) == 64

    loaded = store.load(
        tenant_id="tenant-1",
        user_id="user-1",
        scope_key="example.com",
    )
    assert loaded == state


def test_session_binding_prevents_cross_scope_decryption(tmp_path: Path) -> None:
    database = _database(tmp_path)
    store = HostedAccountSessionStore(database, bridge_secret=b"h" * 32)
    store.save(
        tenant_id="tenant-1",
        user_id="user-1",
        scope_key="example.com",
        account_id="account-1",
        storage_state={"cookies": [], "origins": []},
    )
    assert (
        store.load(
            tenant_id="tenant-1",
            user_id="user-1",
            scope_key="other.example.com",
        )
        is None
    )
