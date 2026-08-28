from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from munshi_apply_native.database import Database
from munshi_apply_native.models import ResolutionTaskPayload
from munshi_apply_native.resolution_task_store import ResolutionTaskStore


def create_database(tmp_path: Path) -> Database:
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
    return database


def task_payload(**overrides: object) -> ResolutionTaskPayload:
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "taskId": "resolution-1",
        "applicationId": "app-1",
        "sessionId": "session-1",
        "checkpointId": "checkpoint-1",
        "pageId": "page-1",
        "controlId": "control-1",
        "questionId": "question-1",
        "question": "Are you willing to relocate?",
        "semanticType": "RELOCATION",
        "category": "MISSING_FACT",
        "status": "PENDING",
        "riskLevel": "LOW",
        "autoResolvable": True,
        "requiresUser": False,
        "groupingScope": "SEMANTIC",
        "groupKey": "semantic:RELOCATION",
        "sourceRefs": ["requirement-1"],
        "evidenceRefs": [],
        "attemptedResolvers": [],
        "reason": "Relocation preference is not confirmed",
        "resolution": None,
        "createdAt": "2026-08-28T16:00:00.000Z",
        "updatedAt": "2026-08-28T16:00:00.000Z",
    }
    payload.update(overrides)
    return ResolutionTaskPayload.model_validate(payload)


def test_resolution_task_round_trips_and_identical_upsert_is_idempotent(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    store = ResolutionTaskStore(database)
    task = task_payload()

    assert store.upsert(task) is True
    assert store.upsert(task) is False

    stored = store.get("resolution-1")
    assert stored is not None
    assert stored.wire_payload() == task.wire_payload()
    assert stored.checkpoint_id == "checkpoint-1"


def test_resolution_task_can_wait_then_resolve_without_losing_checkpoint(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    store = ResolutionTaskStore(database)
    store.upsert(task_payload())

    waiting = task_payload(
        status="WAITING_FOR_USER",
        requiresUser=True,
        attemptedResolvers=["MASTER_PROFILE"],
        updatedAt="2026-08-28T16:01:00.000Z",
    )
    assert store.upsert(waiting) is False

    resolved = task_payload(
        status="RESOLVED",
        requiresUser=False,
        evidenceRefs=["evidence-relocation"],
        attemptedResolvers=["MASTER_PROFILE", "USER"],
        resolution={
            "value": "Yes",
            "source": "USER",
            "evidenceRefs": ["evidence-relocation"],
            "approvedByUser": True,
            "resolvedAt": "2026-08-28T16:02:00.000Z",
        },
        updatedAt="2026-08-28T16:02:00.000Z",
    )
    store.upsert(resolved)

    stored = store.get("resolution-1")
    assert stored is not None
    assert stored.status == "RESOLVED"
    assert stored.checkpoint_id == "checkpoint-1"
    assert stored.session_id == "session-1"
    assert stored.resolution is not None
    assert stored.resolution.value == "Yes"


def test_terminal_resolution_task_rejects_later_mutation(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    store = ResolutionTaskStore(database)
    resolved = task_payload(
        status="RESOLVED",
        evidenceRefs=["evidence-relocation"],
        attemptedResolvers=["USER"],
        resolution={
            "value": "Yes",
            "source": "USER",
            "evidenceRefs": ["evidence-relocation"],
            "approvedByUser": True,
            "resolvedAt": "2026-08-28T16:02:00.000Z",
        },
        updatedAt="2026-08-28T16:02:00.000Z",
    )
    store.upsert(resolved)

    changed = task_payload(
        status="RESOLVED",
        evidenceRefs=["evidence-other"],
        attemptedResolvers=["USER"],
        resolution={
            "value": "No",
            "source": "USER",
            "evidenceRefs": ["evidence-other"],
            "approvedByUser": True,
            "resolvedAt": "2026-08-28T16:03:00.000Z",
        },
        updatedAt="2026-08-28T16:03:00.000Z",
    )
    with pytest.raises(ValueError, match="Terminal resolution tasks cannot be modified"):
        store.upsert(changed)


def test_resolution_task_immutable_identity_cannot_drift(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    store = ResolutionTaskStore(database)
    store.upsert(task_payload())

    changed = task_payload(
        question="Would you move for this role?",
        updatedAt="2026-08-28T16:01:00.000Z",
    )
    with pytest.raises(ValueError, match="immutable identity"):
        store.upsert(changed)


def test_resolution_task_list_supports_application_status_and_group_filters(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    store = ResolutionTaskStore(database)
    store.upsert(task_payload())
    store.upsert(
        task_payload(
            taskId="resolution-2",
            checkpointId="checkpoint-2",
            controlId="control-2",
            questionId="question-2",
            updatedAt="2026-08-28T16:01:00.000Z",
        )
    )

    assert len(store.list(application_id="app-1")) == 2
    assert len(store.list(status="PENDING")) == 2
    grouped = store.list(group_key="semantic:RELOCATION")
    assert [task.task_id for task in grouped] == ["resolution-2", "resolution-1"]


def test_native_model_rejects_high_risk_ai_and_unsafe_captcha() -> None:
    with pytest.raises(ValidationError, match="High-risk resolution tasks cannot attempt"):
        task_payload(
            riskLevel="HIGH",
            attemptedResolvers=["GROUNDED_AI"],
        )

    with pytest.raises(ValidationError, match="CAPTCHA tasks must require direct user"):
        task_payload(
            category="CAPTCHA",
            groupingScope="NONE",
            groupKey=None,
            autoResolvable=True,
            requiresUser=False,
        )
