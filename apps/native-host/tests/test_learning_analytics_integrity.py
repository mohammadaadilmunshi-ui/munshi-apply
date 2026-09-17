from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.learning_analytics_store import LearningAnalyticsStore


def create_store(tmp_path: Path) -> LearningAnalyticsStore:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return LearningAnalyticsStore(database)


def test_recipe_definition_cannot_be_rewritten_or_reactivated(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    recipe = {
        "recipe_id": "recipe-1",
        "component_fingerprint": "cfp-1",
        "semantic_type": "COUNTRY",
        "site_origin": "https://example.test",
        "actions": [{"type": "FOCUS"}, {"type": "SELECT_EXACT_OPTION"}],
        "version": 1,
        "state": "SHADOW",
        "created_at": now,
        "updated_at": now,
    }
    store.save_recipe(recipe)

    with pytest.raises(ValueError, match="immutable definition"):
        store.save_recipe(
            {
                **recipe,
                "actions": [{"type": "CLICK"}],
            }
        )

    store.save_recipe({**recipe, "state": "PROMOTED"})
    store.save_recipe({**recipe, "state": "ROLLED_BACK"})
    with pytest.raises(ValueError, match="state transition"):
        store.save_recipe({**recipe, "state": "PROMOTED"})


def test_experiment_definition_and_assignment_are_stable(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    experiment = {
        "experiment_id": "resume-layout",
        "label": "Resume layout test",
        "minimum_sample_per_variant": 2,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "variants": [
            {"variant_id": "a", "label": "A", "weight": 1.0},
            {"variant_id": "b", "label": "B", "weight": 1.0},
        ],
    }
    store.save_experiment(experiment)

    assignment = {
        "experiment_id": "resume-layout",
        "subject_id": "application-1",
        "variant_id": "a",
        "assigned_at": now,
    }
    assert store.assign_experiment(assignment) is True
    assert store.assign_experiment(assignment) is False

    with pytest.raises(ValueError, match="different variant"):
        store.assign_experiment({**assignment, "variant_id": "b"})

    with pytest.raises(ValueError, match="immutable definition"):
        store.save_experiment(
            {
                **experiment,
                "variants": [
                    {"variant_id": "a", "label": "A", "weight": 2.0},
                    {"variant_id": "b", "label": "B", "weight": 1.0},
                ],
            }
        )


def test_completed_experiment_cannot_be_reactivated(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    experiment = {
        "experiment_id": "completed-test",
        "label": "Completed test",
        "minimum_sample_per_variant": 1,
        "status": "DRAFT",
        "created_at": now,
        "updated_at": now,
        "variants": [
            {"variant_id": "a", "label": "A", "weight": 1.0},
            {"variant_id": "b", "label": "B", "weight": 1.0},
        ],
    }
    store.save_experiment(experiment)
    store.save_experiment({**experiment, "status": "COMPLETE"})

    with pytest.raises(ValueError, match="status transition"):
        store.save_experiment({**experiment, "status": "ACTIVE"})
