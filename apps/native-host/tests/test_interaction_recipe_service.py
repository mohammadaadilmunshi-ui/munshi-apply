from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.interaction_recipe_service import InteractionRecipeService


def create_service(tmp_path: Path) -> tuple[Database, InteractionRecipeService]:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return database, InteractionRecipeService(database)


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


def payload(attempt_id: str, *, success: bool = True) -> dict[str, object]:
    return {
        "attemptId": attempt_id,
        "applicationId": "app-1",
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-safe123",
        "semanticType": "COUNTRY",
        "strategy": "ARIA_COMBOBOX",
        "success": success,
        "verified": True,
        "failureReason": None if success else "verification failed",
    }


def binding() -> dict[str, object]:
    return {
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-safe123",
        "semanticType": "COUNTRY",
    }


def test_recipe_stays_shadow_then_promotes_after_three_verified_successes(
    tmp_path: Path,
) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    first = service.record(payload("attempt-1"))
    second = service.record(payload("attempt-2"))
    third = service.record(payload("attempt-3"))
    assert first["state"] == "SHADOW"
    assert second["state"] == "SHADOW"
    assert third["state"] == "PROMOTED"
    promoted = service.lookup(binding())
    assert promoted is not None
    assert promoted["strategy"] == "ARIA_COMBOBOX"
    assert promoted["state"] == "PROMOTED"
    assert all("value" not in action for action in promoted["actions"])


def test_promoted_recipe_rolls_back_after_two_verified_failures(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    for index in range(3):
        service.record(payload(f"success-{index}"))
    assert service.lookup(binding()) is not None
    first_failure = service.record(payload("failure-1", success=False))
    second_failure = service.record(payload("failure-2", success=False))
    assert first_failure["state"] == "PROMOTED"
    assert second_failure["state"] == "ROLLED_BACK"
    assert service.lookup(binding()) is None


def test_duplicate_attempt_is_idempotent(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    first = service.record(payload("same-attempt"))
    duplicate = service.record(payload("same-attempt"))
    assert first["attemptInserted"] is True
    assert duplicate["attemptInserted"] is False
    assert duplicate["verifiedAttempts"] == 1


def test_rejects_sensitive_semantics_and_unapproved_strategies(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    sensitive = payload("sensitive")
    sensitive["semanticType"] = "WORK_AUTHORIZATION"
    with pytest.raises(ValueError, match="Sensitive"):
        service.record(sensitive)

    unsafe = payload("unsafe")
    unsafe["strategy"] = "FINAL_SUBMIT"
    with pytest.raises(ValueError, match="not eligible"):
        service.record(unsafe)


def test_requires_origin_not_full_application_url(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    request = payload("bad-origin")
    request["siteOrigin"] = "https://jobs.example.test/apply/123?token=x"
    with pytest.raises(ValueError, match="siteOrigin"):
        service.record(request)
