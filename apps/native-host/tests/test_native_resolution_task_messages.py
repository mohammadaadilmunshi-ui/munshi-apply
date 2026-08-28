from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "native-resolution-tasks.sqlite", migrations)
    result.migrate()
    return result


def task_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "taskId": "resolution-native-1",
        "applicationId": "application-native-1",
        "sessionId": "session-native-1",
        "checkpointId": "checkpoint-native-1",
        "pageId": "page-native-1",
        "controlId": "control-native-1",
        "questionId": "question-native-1",
        "question": "Are you willing to relocate?",
        "semanticType": "RELOCATION",
        "category": "MISSING_FACT",
        "status": "PENDING",
        "riskLevel": "LOW",
        "autoResolvable": True,
        "requiresUser": False,
        "groupingScope": "SEMANTIC",
        "groupKey": "semantic:RELOCATION",
        "sourceRefs": ["requirement-native-1"],
        "evidenceRefs": [],
        "attemptedResolvers": [],
        "reason": "Relocation preference is not confirmed",
        "resolution": None,
        "createdAt": "2026-08-28T18:00:00.000Z",
        "updatedAt": "2026-08-28T18:00:00.000Z",
    }
    payload.update(overrides)
    return payload


def test_native_resolution_task_upsert_get_and_list_round_trip(tmp_path: Path) -> None:
    db = database(tmp_path)
    message = {"type": "UPSERT_RESOLUTION_TASK", "payload": task_payload()}

    first = handle(message, db)
    second = handle(message, db)
    fetched = handle(
        {
            "type": "GET_RESOLUTION_TASK",
            "payload": {"taskId": "resolution-native-1"},
        },
        db,
    )
    listed = handle(
        {
            "type": "LIST_RESOLUTION_TASKS",
            "payload": {
                "applicationId": "application-native-1",
                "status": "PENDING",
                "groupKey": "semantic:RELOCATION",
                "limit": 25,
            },
        },
        db,
    )

    assert first["ok"] is True
    assert first["data"]["created"] is True  # type: ignore[index]
    assert second["data"]["created"] is False  # type: ignore[index]
    assert fetched["data"]["checkpointId"] == "checkpoint-native-1"  # type: ignore[index]
    assert listed["data"][0]["taskId"] == "resolution-native-1"  # type: ignore[index]

    with db.connect() as connection:
        application = connection.execute(
            "SELECT application_id FROM applications WHERE application_id = ?",
            ("application-native-1",),
        ).fetchone()
    assert application is not None


def test_native_resolution_task_supports_waiting_then_resolved_updates(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    handle({"type": "UPSERT_RESOLUTION_TASK", "payload": task_payload()}, db)
    waiting = task_payload(
        status="WAITING_FOR_USER",
        requiresUser=True,
        attemptedResolvers=["MASTER_PROFILE"],
        updatedAt="2026-08-28T18:01:00.000Z",
    )
    handle({"type": "UPSERT_RESOLUTION_TASK", "payload": waiting}, db)
    resolved = task_payload(
        status="RESOLVED",
        requiresUser=False,
        evidenceRefs=["evidence-native-1"],
        attemptedResolvers=["MASTER_PROFILE", "USER"],
        resolution={
            "value": "Yes",
            "source": "USER",
            "evidenceRefs": ["evidence-native-1"],
            "approvedByUser": True,
            "resolvedAt": "2026-08-28T18:02:00.000Z",
        },
        updatedAt="2026-08-28T18:02:00.000Z",
    )
    result = handle({"type": "UPSERT_RESOLUTION_TASK", "payload": resolved}, db)

    assert result["data"]["task"]["status"] == "RESOLVED"  # type: ignore[index]
    assert result["data"]["task"]["checkpointId"] == "checkpoint-native-1"  # type: ignore[index]
    assert result["data"]["task"]["resolution"]["value"] == "Yes"  # type: ignore[index]


def test_native_resolution_task_list_rejects_invalid_filters(tmp_path: Path) -> None:
    db = database(tmp_path)
    with pytest.raises(ValueError, match="status is invalid"):
        handle(
            {
                "type": "LIST_RESOLUTION_TASKS",
                "payload": {"status": "UNKNOWN"},
            },
            db,
        )
    with pytest.raises(ValueError, match="limit must be between"):
        handle(
            {
                "type": "LIST_RESOLUTION_TASKS",
                "payload": {"limit": 501},
            },
            db,
        )


def test_native_resolution_task_upsert_keeps_high_risk_validation(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="High-risk resolution tasks cannot attempt"):
        handle(
            {
                "type": "UPSERT_RESOLUTION_TASK",
                "payload": task_payload(
                    riskLevel="HIGH",
                    attemptedResolvers=["GROUNDED_AI"],
                ),
            },
            database(tmp_path),
        )


def test_native_health_advertises_resolution_tasks(tmp_path: Path) -> None:
    response = handle({"type": "PING"}, database(tmp_path))
    assert response["ok"] is True
    assert response["data"]["protocol_version"] == 3  # type: ignore[index]
    assert response["data"]["capabilities"]["resolution_tasks"] is True  # type: ignore[index]
