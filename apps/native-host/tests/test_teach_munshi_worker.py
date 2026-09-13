from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.interaction_recipe_service import InteractionRecipeService
from munshi_apply_native.teach_munshi_service import TeachMunshiService
from munshi_apply_native.teach_munshi_worker import (
    TeachMunshiLearningWorker,
    run_teach_munshi_learning_worker,
)


def _database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "teach-worker.sqlite", migrations)
    database.migrate()
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-worker', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (now, now),
        )
    return database


def _lesson(observation_id: str) -> dict[str, object]:
    return {
        "observationId": observation_id,
        "applicationId": "app-worker",
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-worker-country",
        "semanticType": "COUNTRY",
        "atsFamily": "workday",
        "tenantKey": "company-worker",
        "uiFingerprint": "uif-worker-v1",
        "questionFingerprint": "qfp-worker-country",
        "teacherKind": "MODEL",
        "teacherProvider": "anthropic",
        "sourceLane": "MODEL_RECIPE_PROPOSAL",
        "actions": [
            {"type": "FOCUS"},
            {"type": "CLICK"},
            {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
            {"type": "SELECT_EXACT_OPTION"},
            {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
        ],
        "verifiedSuccess": True,
    }


def _recipe_lookup(database: Database) -> dict[str, object] | None:
    return InteractionRecipeService(database).lookup(
        {
            "siteOrigin": "https://jobs.example.test",
            "componentFingerprint": "cfp-worker-country",
            "semanticType": "COUNTRY",
            "atsFamily": "WORKDAY",
            "tenantKey": "company-worker",
            "uiFingerprint": "uif-worker-v1",
            "questionFingerprint": "qfp-worker-country",
        }
    )


def test_worker_drain_is_local_and_creates_shadow_recipe(tmp_path: Path) -> None:
    database = _database(tmp_path)
    captured = TeachMunshiService(database).capture(_lesson("worker-once"))
    assert captured["providerCallMade"] is False

    worker = TeachMunshiLearningWorker(database, batch_size=8)
    assert worker.drain_once() == 1

    recipe = _recipe_lookup(database)
    assert recipe is not None
    assert recipe["state"] == "SHADOW"
    assert recipe["verifiedSuccesses"] == 1


def test_worker_promotes_after_three_independent_verified_lessons(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = TeachMunshiService(database)
    worker = TeachMunshiLearningWorker(database, batch_size=1)

    for index in range(3):
        captured = service.capture(_lesson(f"worker-success-{index}"))
        assert captured["providerCallMade"] is False
        assert worker.drain_once() == 1

    recipe = _recipe_lookup(database)
    assert recipe is not None
    assert recipe["state"] == "PROMOTED"
    assert recipe["verifiedSuccesses"] == 3


def test_async_worker_processes_queue_without_application_wait(tmp_path: Path) -> None:
    database = _database(tmp_path)
    TeachMunshiService(database).capture(_lesson("worker-async"))
    worker = TeachMunshiLearningWorker(database, batch_size=8)

    async def exercise() -> None:
        stop_event = asyncio.Event()
        task = asyncio.create_task(
            run_teach_munshi_learning_worker(
                worker,
                stop_event,
                poll_seconds=0.01,
            )
        )
        for _ in range(100):
            if _recipe_lookup(database) is not None:
                break
            await asyncio.sleep(0.01)
        stop_event.set()
        await task

    asyncio.run(exercise())

    recipe = _recipe_lookup(database)
    assert recipe is not None
    assert recipe["verifiedSuccesses"] == 1
