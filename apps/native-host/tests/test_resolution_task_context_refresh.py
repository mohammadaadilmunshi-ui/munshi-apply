from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.models import ResolutionTaskPayload
from munshi_apply_native.resolution_task_store import ResolutionTaskStore


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "resolution-context.sqlite", migrations)
    database.migrate()
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-context', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (now, now),
        )
    return database


def task_payload(**overrides: object) -> ResolutionTaskPayload:
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "taskId": "resolution-preflight-stable",
        "applicationId": "app-context",
        "sessionId": "session-1",
        "checkpointId": "checkpoint-1",
        "pageId": "page-1",
        "controlId": "control-1",
        "questionId": "question-1",
        "question": "Will you require employment sponsorship in the future?",
        "semanticType": "SPONSORSHIP_FUTURE",
        "category": "MISSING_FACT",
        "status": "PENDING",
        "riskLevel": "HIGH",
        "autoResolvable": True,
        "requiresUser": False,
        "groupingScope": "SEMANTIC",
        "groupKey": "semantic:SPONSORSHIP_FUTURE",
        "sourceRefs": ["req-sponsorship"],
        "evidenceRefs": [],
        "attemptedResolvers": [],
        "reason": "A confirmed candidate answer is required",
        "resolution": None,
        "createdAt": "2026-08-28T18:30:00.000Z",
        "updatedAt": "2026-08-28T18:30:00.000Z",
    }
    payload.update(overrides)
    return ResolutionTaskPayload.model_validate(payload)


def test_nonterminal_task_refreshes_execution_context(tmp_path: Path) -> None:
    store = ResolutionTaskStore(create_database(tmp_path))
    store.upsert(task_payload())

    refreshed = task_payload(
        sessionId="session-2",
        checkpointId="checkpoint-2",
        pageId="page-2",
        controlId="control-2",
        questionId="question-2",
        updatedAt="2026-08-28T18:31:00.000Z",
    )
    assert store.upsert(refreshed) is False

    stored = store.get("resolution-preflight-stable")
    assert stored is not None
    assert stored.session_id == "session-2"
    assert stored.checkpoint_id == "checkpoint-2"
    assert stored.page_id == "page-2"
    assert stored.control_id == "control-2"
    assert stored.question_id == "question-2"


def test_nonterminal_task_can_tighten_preflight_classification(tmp_path: Path) -> None:
    store = ResolutionTaskStore(create_database(tmp_path))
    store.upsert(task_payload())

    review = task_payload(
        category="LEGAL_CONFIRMATION",
        autoResolvable=False,
        requiresUser=True,
        groupingScope="SEMANTIC",
        groupKey="semantic:SPONSORSHIP_FUTURE",
        reason="The answer needs explicit owner confirmation",
        updatedAt="2026-08-28T18:31:00.000Z",
    )
    store.upsert(review)

    stored = store.get("resolution-preflight-stable")
    assert stored is not None
    assert stored.category == "LEGAL_CONFIRMATION"
    assert stored.risk_level == "HIGH"
    assert stored.auto_resolvable is False
    assert stored.requires_user is True
    assert stored.reason == "The answer needs explicit owner confirmation"


def test_true_logical_identity_still_cannot_drift(tmp_path: Path) -> None:
    store = ResolutionTaskStore(create_database(tmp_path))
    store.upsert(task_payload())

    with pytest.raises(ValueError, match="immutable identity"):
        store.upsert(
            task_payload(
                sourceRefs=["different-requirement"],
                updatedAt="2026-08-28T18:31:00.000Z",
            )
        )


def test_terminal_task_still_rejects_context_refresh(tmp_path: Path) -> None:
    store = ResolutionTaskStore(create_database(tmp_path))
    resolved = task_payload(
        status="RESOLVED",
        requiresUser=False,
        evidenceRefs=["evidence-1"],
        attemptedResolvers=["USER"],
        resolution={
            "value": "No",
            "source": "USER",
            "evidenceRefs": ["evidence-1"],
            "approvedByUser": True,
            "resolvedAt": "2026-08-28T18:31:00.000Z",
        },
        updatedAt="2026-08-28T18:31:00.000Z",
    )
    store.upsert(resolved)

    with pytest.raises(ValueError, match="Terminal resolution tasks cannot be modified"):
        store.upsert(
            task_payload(
                status="RESOLVED",
                sessionId="session-2",
                checkpointId="checkpoint-2",
                evidenceRefs=["evidence-1"],
                attemptedResolvers=["USER"],
                resolution={
                    "value": "No",
                    "source": "USER",
                    "evidenceRefs": ["evidence-1"],
                    "approvedByUser": True,
                    "resolvedAt": "2026-08-28T18:31:00.000Z",
                },
                updatedAt="2026-08-28T18:32:00.000Z",
            )
        )
