from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return database


def test_ensure_application_is_idempotent_and_unlocks_checkpoint_fk(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    ensure = {
        "type": "ENSURE_APPLICATION",
        "payload": {
            "applicationId": "app-controller-1",
            "observedAt": "2026-08-14T21:00:00Z",
        },
    }

    first = handle(ensure, database)
    second = handle(ensure, database)

    assert first["ok"] is True
    assert first["data"]["created"] is True  # type: ignore[index]
    assert second["data"]["created"] is False  # type: ignore[index]

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT application_id, status, created_at, updated_at
            FROM applications
            WHERE application_id = ?
            """,
            ("app-controller-1",),
        ).fetchone()
    assert row is not None
    assert row["status"] == "DETECTED"
    assert row["created_at"] == "2026-08-14T21:00:00Z"

    checkpoint = {
        "checkpointId": "cp-controller-0",
        "applicationId": "app-controller-1",
        "sequence": 0,
        "state": "PERSONAL",
        "pageId": "page-1",
        "pageFingerprint": "fingerprint-1",
        "completedControlIds": [],
        "pendingControlIds": [],
        "selectedResumeId": None,
        "selectedResumeSha256": None,
        "createdAt": "2026-08-14T21:00:01Z",
    }
    saved = handle(
        {"type": "SAVE_APPLICATION_CHECKPOINT", "payload": checkpoint},
        database,
    )
    assert saved["ok"] is True
    assert saved["data"]["created"] is True  # type: ignore[index]


@pytest.mark.parametrize(
    "payload,error",
    [
        (
            {"applicationId": "", "observedAt": "2026-08-14T21:00:00Z"},
            "applicationId",
        ),
        (
            {"applicationId": "app-1", "observedAt": "not-a-date"},
            "ISO timestamp",
        ),
        (
            {"applicationId": "app-1", "observedAt": "2026-08-14T21:00:00"},
            "timezone",
        ),
    ],
)
def test_ensure_application_rejects_invalid_identity_or_timestamp(
    tmp_path: Path,
    payload: dict[str, object],
    error: str,
) -> None:
    database = create_database(tmp_path)
    with pytest.raises(ValueError, match=error):
        handle({"type": "ENSURE_APPLICATION", "payload": payload}, database)
