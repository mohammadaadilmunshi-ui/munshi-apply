from __future__ import annotations

from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.interaction_recipe_service import InteractionRecipeService
from munshi_apply_native.teach_munshi_telegram import TeachMunshiTelegramWorker


def _database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "teach-telegram.sqlite", migrations)
    database.migrate()
    return database


def _promote_recipe(database: Database) -> dict[str, object]:
    service = InteractionRecipeService(database)
    learned: dict[str, object] | None = None
    for index in range(3):
        learned = service.record(
            {
                "attemptId": f"attempt-{index}",
                "applicationId": "application-test",
                "siteOrigin": "https://jobs.example.test",
                "componentFingerprint": "cfp-example-control",
                "semanticType": "WORK_AUTH_US",
                "strategy": "ARIA_COMBOBOX",
                "success": True,
                "verified": True,
                "failureReason": None,
                "atsFamily": "workday",
                "tenantKey": "example-tenant",
                "uiFingerprint": "ui-v1",
                "questionFingerprint": "question-v1",
            }
        )
    assert learned is not None
    assert learned["state"] == "PROMOTED"
    return learned


def test_promoted_and_rolled_back_recipes_notify_once(tmp_path: Path) -> None:
    database = _database(tmp_path)
    recipe = _promote_recipe(database)
    deliveries: list[str] = []

    worker = TeachMunshiTelegramWorker(
        database,
        "existing-hunter-bot-token",
        "123456",
        sender=lambda _token, _chat, text, _timeout: deliveries.append(text),
    )

    first = worker.deliver_due()
    assert first.discovered == 1
    assert first.delivered == 1
    assert len(deliveries) == 1
    assert "SHADOW → PROMOTED" in deliveries[0]
    assert "WORK_AUTH_US" not in deliveries[0]
    assert "application-test" not in deliveries[0]

    duplicate = worker.deliver_due()
    assert duplicate.discovered == 0
    assert duplicate.delivered == 0
    assert len(deliveries) == 1

    service = InteractionRecipeService(database)
    for index in range(2):
        recipe = service.record_outcome(
            {
                "recipeId": recipe["recipeId"],
                "attemptId": f"failure-{index}",
                "applicationId": "application-test",
                "success": False,
                "verified": True,
                "failureReason": "verification_failed",
            }
        )
    assert recipe["state"] == "ROLLED_BACK"

    rollback = worker.deliver_due()
    assert rollback.discovered == 1
    assert rollback.delivered == 1
    assert len(deliveries) == 2
    assert "PROMOTED → ROLLED BACK" in deliveries[1]
    assert "Candidate answer values are not included" in deliveries[1]


def test_outbox_persists_only_allowlisted_metadata(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _promote_recipe(database)
    worker = TeachMunshiTelegramWorker(
        database,
        "existing-hunter-bot-token",
        "123456",
        sender=lambda *_args: None,
    )

    assert worker.discover_events() == 1
    with database.connect() as connection:
        row = connection.execute(
            "SELECT payload_json FROM teach_munshi_telegram_outbox"
        ).fetchone()
    assert row is not None
    payload = str(row["payload_json"])
    assert "application-test" not in payload
    assert "WORK_AUTH_US" not in payload
    assert "question-v1" not in payload
    assert "example-tenant" not in payload
    assert "answer" not in payload.lower()


def test_delivery_failure_is_non_blocking_and_retryable(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _promote_recipe(database)

    def failing_sender(*_args: object) -> None:
        raise RuntimeError("telegram_transport_timeout")

    worker = TeachMunshiTelegramWorker(
        database,
        "secret-token-must-never-be-stored-in-error",
        "123456",
        sender=failing_sender,
    )
    result = worker.deliver_due()
    assert result.delivered == 0
    assert result.retry == 1

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT delivery_state, last_error
            FROM teach_munshi_telegram_outbox
            """
        ).fetchone()
    assert row is not None
    assert row["delivery_state"] == "PENDING"
    assert row["last_error"] == "telegram_transport_timeout"
    assert "secret-token" not in str(row["last_error"])
