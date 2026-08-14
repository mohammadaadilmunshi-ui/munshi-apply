from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "native-profile.sqlite", migrations)
    result.migrate()
    return result


def test_native_profile_snapshot_protocol_round_trip(tmp_path: Path) -> None:
    db = database(tmp_path)
    now = datetime.now(UTC).isoformat()
    profile = {
        "profileId": "profile-1",
        "displayName": "Application profile",
        "facts": [],
        "records": [
            {
                "recordId": "project-1",
                "kind": "PROJECT",
                "label": "Project A",
                "facts": [],
                "sortOrder": 0,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "recordTombstones": [],
        "createdAt": now,
        "updatedAt": now,
        "schemaVersion": 1,
        "snapshotVersion": 1,
    }

    assert handle(
        {"type": "SAVE_PROFILE_SNAPSHOT", "payload": profile}, db
    ) == {"ok": True}
    assert handle({"type": "GET_PROFILE_SNAPSHOT"}, db) == {
        "ok": True,
        "data": profile,
    }


def test_native_profile_save_rejects_non_object_payload(tmp_path: Path) -> None:
    db = database(tmp_path)
    try:
        handle({"type": "SAVE_PROFILE_SNAPSHOT", "payload": "invalid"}, db)
    except ValueError as error:
        assert "must be an object" in str(error)
    else:
        raise AssertionError("Non-object profile payload was accepted")
