from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import munshi_apply_native.ai_governance as ai_governance
from munshi_apply_native.ai_settings import AIConfiguration, AISettingsStore
from munshi_apply_native.application_store import ApplicationStore
from munshi_apply_native.architecture_store import ArchitectureStore
from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle


def create_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Database, AISettingsStore]:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    now = datetime(2026, 8, 14, 18, 0, tzinfo=UTC).isoformat()
    ApplicationStore(database).ensure("app-1", now)
    ArchitectureStore(database).upsert_evidence_node(
        {
            "evidence_id": "ev-1",
            "application_id": "app-1",
            "kind": "EMPLOYMENT",
            "text": "Verified recruiting operations experience",
            "semantic_types": ["WHY_ROLE"],
            "trust_level": "VERIFIED",
            "protected": False,
            "source": "job-listing",
            "updated_at": now,
        }
    )
    store = AISettingsStore(tmp_path / "runtime")
    store.save(
        AIConfiguration.from_payload(
            {
                "provider": "openai",
                "enabled": True,
                "model": "gpt-5.6-luna",
                "monthlyBudgetUsd": 5,
                "warningBudgetUsd": 4,
                "hardStop": True,
                "allowApplicationDrafts": True,
                "allowProfileEvidence": True,
                "allowResumeEvidence": True,
            }
        )
    )
    monkeypatch.setattr(store, "key_source", lambda: "keychain")
    monkeypatch.setattr(store, "_keychain_read", lambda: "test-key-" + ("x" * 40))
    monkeypatch.setattr(
        ai_governance, "_default_clock", lambda: datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
    )
    return database, store


def test_control_status_never_exposes_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, store = create_runtime(tmp_path, monkeypatch)
    result = handle({"type": "GET_AI_CONTROL_STATUS"}, database, store)
    assert result["ok"] is True
    serialized = str(result)
    assert "test-key-" not in serialized
    data = result["data"]
    assert isinstance(data, dict)
    assert data["guardrails"]["ownerReviewRequired"] is True


def test_preview_message_is_provider_free_and_review_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, store = create_runtime(tmp_path, monkeypatch)
    result = handle(
        {
            "type": "PREVIEW_AI_DRAFT",
            "payload": {
                "applicationId": "app-1",
                "pageId": "page-1",
                "questionId": "q-1",
                "controlId": "control-1",
                "question": "Why this role?",
                "semanticType": "WHY_ROLE",
                "correlationId": "q-1",
            },
        },
        database,
        store,
    )
    assert result["ok"] is True
    data = result["data"]
    assert isinstance(data, dict)
    assert data["providerCallMade"] is False
    assert data["reviewRequired"] is True


def test_native_settings_round_trip_new_owner_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, store = create_runtime(tmp_path, monkeypatch)
    result = handle(
        {
            "type": "SAVE_AI_SETTINGS",
            "payload": {
                "provider": "openai",
                "enabled": False,
                "model": "gpt-5.6-luna",
                "monthlyBudgetUsd": 3,
                "warningBudgetUsd": 2,
                "hardStop": True,
                "allowApplicationDrafts": False,
                "allowProfileEvidence": False,
                "allowResumeEvidence": True,
            },
        },
        database,
        store,
    )
    assert result["ok"] is True
    data = result["data"]
    assert isinstance(data, dict)
    assert data["allowApplicationDrafts"] is False
    assert data["allowProfileEvidence"] is False
    assert data["allowResumeEvidence"] is True
