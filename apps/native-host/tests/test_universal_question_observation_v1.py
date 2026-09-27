from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from munshi_apply_native.database import Database
from munshi_apply_native.models import ResolutionTaskPayload
from munshi_apply_native.resolution_task_store import ResolutionTaskStore


def _payload(observation):
    now = datetime.now(UTC)
    return {
        "schemaVersion": 1,
        "taskId": "task-observation-1",
        "applicationId": "app-observation-1",
        "sessionId": "session-observation-1",
        "checkpointId": "checkpoint-observation-1",
        "pageId": "page-observation-1",
        "controlId": "control-observation-1",
        "questionId": "question-observation-1",
        "question": "State New Jersey",
        "semanticType": "UNKNOWN",
        "questionObservation": observation,
        "category": "MISSING_FACT",
        "status": "WAITING_FOR_USER",
        "riskLevel": "MEDIUM",
        "autoResolvable": False,
        "requiresUser": True,
        "groupingScope": "EXACT_QUESTION",
        "groupKey": "state-question",
        "sourceRefs": ["application-plan:plan-1", "sensitivity:NORMAL"],
        "evidenceRefs": [],
        "attemptedResolvers": ["CURRENT_SESSION", "APPROVED_ANSWER_MEMORY"],
        "reason": "Required field has no safe execution value",
        "resolution": None,
        "createdAt": now,
        "updatedAt": now,
    }


def _seed_application(database: Database) -> None:
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO applications(application_id, status, created_at, updated_at) "
            "VALUES ('app-observation-1','QUESTIONS',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )


def test_question_observation_is_structural_and_persists_round_trip(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "apply.sqlite", migrations)
    database.migrate()
    _seed_application(database)
    observation = {
        "raw_question": "State New Jersey",
        "label": "State",
        "section_heading": "Contact Information",
        "nearby_text": "City Postal code Country",
        "placeholder": "",
        "name": "state",
        "id": "state-control",
        "autocomplete": "",
        "input_type": "select",
        "role": "combobox",
        "options": ["New Jersey", "New York", "Pennsylvania"],
        "apply_semantic_type": "UNKNOWN",
        "apply_semantic_confidence": 0.0,
        "control_id": "control-observation-1",
        "page_id": "page-observation-1",
        "repeat_group": None,
        "repeat_index": None,
    }
    task = ResolutionTaskPayload.model_validate(_payload(observation))
    store = ResolutionTaskStore(database)
    assert store.upsert(task) is True
    loaded = store.get(task.task_id)
    assert loaded is not None
    assert loaded.question_observation == observation
    with database.connect() as connection:
        raw = connection.execute(
            "SELECT question_observation_json FROM resolution_tasks WHERE task_id=?",
            (task.task_id,),
        ).fetchone()[0]
    # Employer option/label metadata is structural, not candidate authority.
    assert "New Jersey" in raw
    assert "canonical_answer" not in raw
    assert "execution_value" not in raw


@pytest.mark.parametrize(
    "observation",
    [
        {"raw_question": "State", "value": "New Jersey"},
        {"raw_question": "Email", "canonical_answer": "candidate@example.test"},
        {"raw_question": "Password", "password": "secret"},
        {"raw_question": "OTP", "nested": {"otp": "123456"}},
        {"raw_question": "CAPTCHA", "captcha": "challenge material"},
    ],
)
def test_question_observation_rejects_candidate_values_and_security_material(observation) -> None:
    with pytest.raises(ValidationError, match="candidate values or secrets"):
        ResolutionTaskPayload.model_validate(_payload(observation))
