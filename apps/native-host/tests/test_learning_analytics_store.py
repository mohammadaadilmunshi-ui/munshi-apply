from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.learning_analytics_store import LearningAnalyticsStore


def create_store(tmp_path: Path) -> tuple[Database, LearningAnalyticsStore]:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return database, LearningAnalyticsStore(database)


def insert_application(database: Database, application_id: str = "app-1") -> None:
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES (?, NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (application_id, now, now),
        )


def test_recipe_round_trip_and_attempt_idempotency(tmp_path: Path) -> None:
    database, store = create_store(tmp_path)
    insert_application(database)
    now = datetime.now(UTC).isoformat()
    store.save_recipe(
        {
            "recipe_id": "recipe-1",
            "component_fingerprint": "cfp-1",
            "semantic_type": "COUNTRY",
            "site_origin": "https://example.test",
            "actions": [
                {"type": "FOCUS"},
                {"type": "SELECT_EXACT_OPTION"},
            ],
            "version": 1,
            "state": "SHADOW",
            "created_at": now,
            "updated_at": now,
        }
    )
    recipe = store.recipe("recipe-1")
    assert recipe is not None
    assert recipe["actions"] == [
        {"type": "FOCUS"},
        {"type": "SELECT_EXACT_OPTION"},
    ]

    attempt = {
        "attempt_id": "attempt-1",
        "recipe_id": "recipe-1",
        "application_id": "app-1",
        "occurred_at": now,
        "success": True,
        "verified": True,
        "failure_reason": None,
    }
    assert store.record_recipe_attempt(attempt) is True
    assert store.record_recipe_attempt(attempt) is False
    attempts = store.recipe_attempts("recipe-1")
    assert len(attempts) == 1
    assert attempts[0]["success"] is True
    assert attempts[0]["verified"] is True


def test_outcomes_are_append_only_and_idempotent(tmp_path: Path) -> None:
    database, store = create_store(tmp_path)
    insert_application(database)
    now = datetime.now(UTC).isoformat()
    outcome = {
        "outcome_event_id": "outcome-1",
        "application_id": "app-1",
        "stage": "INTERVIEW",
        "occurred_at": now,
        "source": "owner-confirmed",
    }
    assert store.record_outcome(outcome) is True
    assert store.record_outcome(outcome) is False
    assert store.application_outcomes("app-1") == [outcome]


def test_attribution_tokens_are_opaque_and_revocable(tmp_path: Path) -> None:
    database, store = create_store(tmp_path)
    insert_application(database)
    now = datetime.now(UTC).isoformat()

    with pytest.raises(ValueError, match="opaque"):
        store.create_attribution_token("job=secret", "app-1", now)

    store.create_attribution_token("7KQ2N9X4_abcd", "app-1", now)
    assert store.revoke_attribution_token("7KQ2N9X4_abcd", now) is True
    assert store.revoke_attribution_token("7KQ2N9X4_abcd", now) is False


def test_experiment_and_assignment_persistence_is_idempotent(tmp_path: Path) -> None:
    _, store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    store.save_experiment(
        {
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
    )
    assignment = {
        "experiment_id": "resume-layout",
        "subject_id": "app-1",
        "variant_id": "a",
        "assigned_at": now,
    }
    assert store.assign_experiment(assignment) is True
    assert store.assign_experiment(assignment) is False
    assert store.experiment_assignments("resume-layout") == [assignment]


def test_experiment_requires_multiple_variants(tmp_path: Path) -> None:
    _, store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    with pytest.raises(ValueError, match="at least two variants"):
        store.save_experiment(
            {
                "experiment_id": "invalid",
                "label": "Invalid",
                "minimum_sample_per_variant": 1,
                "status": "ACTIVE",
                "created_at": now,
                "updated_at": now,
                "variants": [{"variant_id": "a", "label": "A", "weight": 1.0}],
            }
        )
