from __future__ import annotations

from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.interaction_recipe_listing import list_interaction_recipes
from munshi_apply_native.interaction_recipe_service import InteractionRecipeService


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return database


def test_learning_inventory_is_owner_visible_but_value_free(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    service = InteractionRecipeService(database)
    payload = {
        "attemptId": "attempt-listing",
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-listing123",
        "semanticType": "COUNTRY",
        "strategy": "ARIA_COMBOBOX",
        "success": True,
        "verified": True,
        "failureReason": None,
    }
    service.record(payload)

    lessons = list_interaction_recipes(database)

    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson["siteOrigin"] == "https://jobs.example.test"
    assert lesson["semanticType"] == "COUNTRY"
    assert lesson["state"] == "SHADOW"
    assert lesson["verifiedAttempts"] == 1
    assert lesson["verifiedSuccesses"] == 1
    assert lesson["actionCount"] > 0
    assert "actions" not in lesson
    assert "value" not in str(lesson).lower()
