from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-1', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (now, now),
        )
    return database


def attempt(index: int) -> dict[str, object]:
    return {
        "attemptId": f"attempt-{index}",
        "applicationId": "app-1",
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-message",
        "semanticType": "COUNTRY",
        "strategy": "ARIA_COMBOBOX",
        "success": True,
        "verified": True,
        "failureReason": None,
    }


def test_native_recipe_messages_promote_and_lookup(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    for index in range(3):
        response = handle(
            {
                "type": "RECORD_INTERACTION_RECIPE_ATTEMPT",
                "payload": attempt(index),
            },
            database,
        )
        assert response["ok"] is True
    lookup = handle(
        {
            "type": "GET_INTERACTION_RECIPE",
            "payload": {
                "siteOrigin": "https://jobs.example.test",
                "componentFingerprint": "cfp-message",
                "semanticType": "COUNTRY",
            },
        },
        database,
    )
    assert lookup["ok"] is True
    assert lookup["data"] is not None
    assert lookup["data"]["state"] == "PROMOTED"
    assert lookup["data"]["strategy"] == "ARIA_COMBOBOX"
