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


def contextual_payload(attempt_id: str, *, tenant: str = "tenant-a") -> dict[str, object]:
    return {
        **payload(attempt_id),
        "atsFamily": "workday",
        "tenantKey": tenant,
        "uiFingerprint": "uif-workday-country-v1",
        "questionFingerprint": "qfp-country",
    }


def binding(semantic_type: str = "COUNTRY") -> dict[str, object]:
    return {
        "siteOrigin": "https://jobs.example.test",
        "componentFingerprint": "cfp-safe123",
        "semanticType": semantic_type,
    }


def taught_actions() -> list[dict[str, object]]:
    return [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "TYPE", "valueSource": "ANSWER"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ]


def test_recipe_stays_shadow_then_promotes_after_three_verified_successes(tmp_path: Path) -> None:
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


def test_promoted_recipe_rolls_back_and_quarantines_after_two_verified_failures(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    for index in range(3):
        service.record(payload(f"success-{index}"))
    promoted = service.lookup(binding())
    assert promoted is not None
    first_failure = service.record_outcome(
        {
            "recipeId": promoted["recipeId"],
            "attemptId": "failure-1",
            "applicationId": "app-1",
            "success": False,
            "verified": True,
            "failureReason": "verification failed",
        }
    )
    second_failure = service.record_outcome(
        {
            "recipeId": promoted["recipeId"],
            "attemptId": "failure-2",
            "applicationId": "app-1",
            "success": False,
            "verified": True,
            "failureReason": "verification failed",
        }
    )
    assert first_failure["state"] == "PROMOTED"
    assert second_failure["state"] == "ROLLED_BACK"
    assert second_failure["knowledgeState"] == "QUARANTINED"
    assert service.lookup(binding()) is None


def test_duplicate_attempt_is_idempotent(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    first = service.record(payload("same-attempt"))
    duplicate = service.record(payload("same-attempt"))
    assert first["attemptInserted"] is True
    assert duplicate["attemptInserted"] is False
    assert duplicate["verifiedAttempts"] == 1
    assert duplicate["verifiedSuccesses"] == 1


def test_taught_recipe_requires_three_verified_successes_before_promotion(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    taught = service.teach(
        {
            **binding(),
            "attemptId": "owner-demo",
            "applicationId": "app-1",
            "actions": taught_actions(),
        }
    )
    assert taught["strategy"] == "TAUGHT_RECIPE"
    assert taught["state"] == "SHADOW"
    assert taught["verifiedAttempts"] == 1
    assert "United States" not in str(taught)
    candidate = service.lookup(binding())
    assert candidate is not None
    assert candidate["recipeId"] == taught["recipeId"]
    second = service.record_outcome(
        {
            "recipeId": taught["recipeId"],
            "attemptId": "automatic-trial-1",
            "applicationId": "app-1",
            "success": True,
            "verified": True,
            "failureReason": None,
        }
    )
    assert second["state"] == "SHADOW"
    promoted = service.record_outcome(
        {
            "recipeId": taught["recipeId"],
            "attemptId": "automatic-trial-2",
            "applicationId": "app-1",
            "success": True,
            "verified": True,
            "failureReason": None,
        }
    )
    assert promoted["state"] == "PROMOTED"
    assert promoted["verifiedSuccesses"] == 3


def test_recipe_context_prevents_cross_tenant_or_ui_drift_reuse(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    for index in range(3):
        result = service.record(contextual_payload(f"context-{index}"))
    assert result["state"] == "PROMOTED"
    assert result["atsFamily"] == "WORKDAY"
    assert result["tenantKey"] == "tenant-a"
    assert result["confidence"] > 0.5

    same = service.lookup(
        {
            **binding(),
            "atsFamily": "WORKDAY",
            "tenantKey": "tenant-a",
            "uiFingerprint": "uif-workday-country-v1",
            "questionFingerprint": "qfp-country",
        }
    )
    assert same is not None
    assert same["state"] == "PROMOTED"

    other_tenant = service.lookup(
        {
            **binding(),
            "atsFamily": "WORKDAY",
            "tenantKey": "tenant-b",
            "uiFingerprint": "uif-workday-country-v1",
            "questionFingerprint": "qfp-country",
        }
    )
    assert other_tenant is None

    changed_ui = service.lookup(
        {
            **binding(),
            "atsFamily": "WORKDAY",
            "tenantKey": "tenant-a",
            "uiFingerprint": "uif-workday-country-v2",
            "questionFingerprint": "qfp-country",
        }
    )
    assert changed_ui is None


def test_resolution_cost_summary_tracks_deterministic_and_claude_fallback(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    now = datetime.now(UTC).isoformat()
    assert service.record_resolution(
        {
            "event_id": "resolution-1",
            "application_id": "app-1",
            "site_origin": "https://jobs.example.test",
            "component_fingerprint": "cfp-safe123",
            "semantic_type": "COUNTRY",
            "resolution_lane": "NATIVE_CONTROL",
            "success": True,
            "verified": True,
            "occurred_at": now,
        }
    )
    assert service.record_resolution(
        {
            "event_id": "resolution-2",
            "application_id": "app-1",
            "site_origin": "https://jobs.example.test",
            "component_fingerprint": "cfp-weird456",
            "semantic_type": "CUSTOM_QUESTION",
            "resolution_lane": "CLAUDE_RECIPE_PROPOSAL",
            "success": True,
            "verified": True,
            "ai_provider": "anthropic",
            "ai_model": "sonnet",
            "input_tokens": 4000,
            "output_tokens": 400,
            "ai_cost_usd": 0.012,
            "fallback_reason": "novel reversible widget",
            "occurred_at": now,
        }
    )
    summary = service.cost_summary()
    assert summary["totalResolutions"] == 2
    assert summary["applications"] == 1
    assert summary["deterministicResolutionRate"] == 0.5
    assert summary["claudeFallbackRate"] == 0.5
    assert summary["aiCostUsd"] == 0.012
    assert summary["aiCostPerApplicationUsd"] == 0.012


def test_consequential_widgets_learn_but_security_controls_do_not(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    sponsorship = payload("sponsorship-widget")
    sponsorship["semanticType"] = "SPONSORSHIP_FUTURE"
    assert service.record(sponsorship)["state"] == "SHADOW"

    unsafe = payload("unsafe-security")
    unsafe["semanticType"] = "MFA"
    with pytest.raises(ValueError, match="security"):
        service.record(unsafe)

    unsupported = payload("unsupported")
    unsupported["strategy"] = "FINAL_SUBMIT"
    with pytest.raises(ValueError, match="not eligible"):
        service.record(unsupported)


def test_teach_rejects_value_bearing_or_unsupported_recipe_steps(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    with pytest.raises(ValueError, match="unsupported or value-bearing"):
        service.teach(
            {
                **binding(),
                "attemptId": "bad-demo",
                "applicationId": "app-1",
                "actions": [{"type": "TYPE", "value": "secret answer"}],
            }
        )


def test_requires_origin_not_full_application_url(tmp_path: Path) -> None:
    database, service = create_service(tmp_path)
    insert_application(database)
    request = payload("bad-origin")
    request["siteOrigin"] = "https://jobs.example.test/apply/123?token=x"
    with pytest.raises(ValueError, match="siteOrigin"):
        service.record(request)
