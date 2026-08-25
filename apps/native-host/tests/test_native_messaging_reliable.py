from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.interaction_recipe_service import InteractionRecipeService
from munshi_apply_native.native_messaging_reliable import list_interaction_recipes


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "reliable.sqlite", migrations)
    database.migrate()
    return database


def insert_application(database: Database) -> None:
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


def test_lists_owner_visible_recipe_metadata_without_actions_or_answer_values(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    insert_application(database)
    service = InteractionRecipeService(database)
    service.teach(
        {
            "attemptId": "owner-demo",
            "applicationId": "app-1",
            "siteOrigin": "https://jobs.example.test",
            "componentFingerprint": "cfp-owner123",
            "semanticType": "COUNTRY",
            "actions": [
                {"type": "FOCUS"},
                {"type": "CLICK"},
                {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
                {"type": "TYPE", "valueSource": "ANSWER"},
                {"type": "SELECT_EXACT_OPTION"},
                {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
            ],
        }
    )

    listed = list_interaction_recipes(database)

    assert len(listed) == 1
    assert listed[0]["semanticType"] == "COUNTRY"
    assert listed[0]["state"] == "SHADOW"
    assert listed[0]["verifiedAttempts"] == 1
    assert listed[0]["verifiedSuccesses"] == 1
    assert "actions" not in listed[0]
    assert "United States" not in str(listed)
