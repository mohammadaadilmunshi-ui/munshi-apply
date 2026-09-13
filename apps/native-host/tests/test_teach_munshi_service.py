from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.interaction_recipe_service import InteractionRecipeService
from munshi_apply_native.teach_munshi_service import TeachMunshiError, TeachMunshiService


def create_services(
    tmp_path: Path,
) -> tuple[Database, TeachMunshiService, InteractionRecipeService]:
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
    return database, TeachMunshiService(database), InteractionRecipeService(database)


def actions() -> list[dict[str, object]]:
    return [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "TYPE", "valueSource": "ANSWER"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ]


def lesson(
    observation_id: str,
    *,
    teacher_kind: str = "MODEL",
    provider: str | None = "anthropic",
    semantic_type: str = "COUNTRY",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "observationId": observation_id,
        "applicationId": "app-1",
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-workday-country",
        "semanticType": semantic_type,
        "atsFamily": "workday",
        "tenantKey": "company-a",
        "uiFingerprint": "uif-workday-country-v1",
        "questionFingerprint": "qfp-country",
        "teacherKind": teacher_kind,
        "sourceLane": "MODEL_RECIPE_PROPOSAL",
        "actions": actions(),
        "verifiedSuccess": True,
    }
    if provider is not None:
        payload["teacherProvider"] = provider
    return payload


@pytest.mark.parametrize(
    ("teacher_kind", "provider"),
    [
        ("MODEL", "anthropic"),
        ("MODEL", "openai"),
        ("MODEL", "gemini"),
        ("LOCAL_MODEL", "ollama"),
        ("DETERMINISTIC_RECOVERY", None),
        ("USER_DEMONSTRATION", None),
    ],
)
def test_capture_is_provider_agnostic_and_non_blocking(
    tmp_path: Path,
    teacher_kind: str,
    provider: str | None,
) -> None:
    _, teach, _ = create_services(tmp_path)
    captured = teach.capture(
        lesson("observation-1", teacher_kind=teacher_kind, provider=provider)
    )

    assert captured["queued"] is True
    assert captured["duplicate"] is False
    assert captured["providerCallMade"] is False
    assert captured["criticalPathWork"] == "LOCAL_SQLITE_INSERT_ONLY"


def test_capture_is_idempotent_without_a_second_model_call(tmp_path: Path) -> None:
    _, teach, _ = create_services(tmp_path)
    payload = lesson("same-observation", provider="anthropic")

    first = teach.capture(payload)
    duplicate = teach.capture(payload)

    assert first["lessonId"] == duplicate["lessonId"]
    assert first["duplicate"] is False
    assert duplicate["duplicate"] is True
    assert duplicate["providerCallMade"] is False


def test_security_or_value_bearing_lessons_fail_closed(tmp_path: Path) -> None:
    _, teach, _ = create_services(tmp_path)
    with pytest.raises(TeachMunshiError, match="security"):
        teach.capture(lesson("mfa", semantic_type="MFA"))

    unsafe = lesson("raw-value")
    unsafe["actions"] = [{"type": "TYPE", "value": "United States"}]
    with pytest.raises(TeachMunshiError, match="value-bearing"):
        teach.capture(unsafe)


def test_unverified_interaction_never_becomes_a_lesson(tmp_path: Path) -> None:
    _, teach, _ = create_services(tmp_path)
    payload = lesson("not-verified")
    payload["verifiedSuccess"] = False

    with pytest.raises(TeachMunshiError, match="verified"):
        teach.capture(payload)


def test_background_drain_creates_shadow_without_model_call(tmp_path: Path) -> None:
    _, teach, recipes = create_services(tmp_path)
    teach.capture(lesson("first-success", provider="anthropic"))

    drained = teach.drain(limit=10)
    candidate = recipes.lookup(
        {
            "siteOrigin": "https://jobs.example.test",
            "componentFingerprint": "cfp-workday-country",
            "semanticType": "COUNTRY",
            "atsFamily": "WORKDAY",
            "tenantKey": "company-a",
            "uiFingerprint": "uif-workday-country-v1",
            "questionFingerprint": "qfp-country",
        }
    )

    assert drained["learned"] == 1
    assert drained["providerCallMade"] is False
    assert candidate is not None
    assert candidate["state"] == "SHADOW"
    assert candidate["verifiedSuccesses"] == 1


def test_three_verified_lessons_promote_for_deterministic_reuse(tmp_path: Path) -> None:
    _, teach, recipes = create_services(tmp_path)
    for index, provider in enumerate(("anthropic", "openai", "gemini"), start=1):
        teach.capture(lesson(f"success-{index}", provider=provider))
        assert teach.drain(limit=1)["providerCallMade"] is False

    promoted = recipes.lookup(
        {
            "siteOrigin": "https://jobs.example.test",
            "componentFingerprint": "cfp-workday-country",
            "semanticType": "COUNTRY",
            "atsFamily": "WORKDAY",
            "tenantKey": "company-a",
            "uiFingerprint": "uif-workday-country-v1",
            "questionFingerprint": "qfp-country",
        }
    )

    assert promoted is not None
    assert promoted["state"] == "PROMOTED"
    assert promoted["verifiedSuccesses"] == 3
    assert all("value" not in action for action in promoted["actions"])


def test_promoted_lesson_rolls_back_after_two_verified_failures(tmp_path: Path) -> None:
    _, teach, recipes = create_services(tmp_path)
    for index in range(3):
        teach.capture(lesson(f"success-{index}", provider="anthropic"))
        teach.drain(limit=1)
    promoted = recipes.lookup(
        {
            "siteOrigin": "https://jobs.example.test",
            "componentFingerprint": "cfp-workday-country",
            "semanticType": "COUNTRY",
            "atsFamily": "WORKDAY",
            "tenantKey": "company-a",
            "uiFingerprint": "uif-workday-country-v1",
            "questionFingerprint": "qfp-country",
        }
    )
    assert promoted is not None

    first = recipes.record_outcome(
        {
            "recipeId": promoted["recipeId"],
            "attemptId": "failure-1",
            "applicationId": "app-1",
            "success": False,
            "verified": True,
            "failureReason": "verification failed",
        }
    )
    second = recipes.record_outcome(
        {
            "recipeId": promoted["recipeId"],
            "attemptId": "failure-2",
            "applicationId": "app-1",
            "success": False,
            "verified": True,
            "failureReason": "verification failed",
        }
    )

    assert first["state"] == "PROMOTED"
    assert second["state"] == "ROLLED_BACK"
    assert second["knowledgeState"] == "QUARANTINED"


def test_learning_metrics_preserve_teacher_provider_mix(tmp_path: Path) -> None:
    _, teach, _ = create_services(tmp_path)
    for index, provider in enumerate(("anthropic", "openai", "gemini"), start=1):
        teach.capture(lesson(f"provider-{index}", provider=provider))
    teach.capture(
        lesson(
            "deterministic",
            teacher_kind="DETERMINISTIC_RECOVERY",
            provider=None,
        )
    )
    teach.drain(limit=10)

    metrics = teach.metrics()
    providers = {row["provider"]: row for row in metrics["providers"]}

    assert metrics["totalLessons"] == 4
    assert metrics["learnedLessons"] == 4
    assert providers["anthropic"]["count"] == 1
    assert providers["openai"]["count"] == 1
    assert providers["gemini"]["count"] == 1
    assert providers["non-model"]["count"] == 1
