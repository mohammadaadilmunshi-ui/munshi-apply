from __future__ import annotations

import pytest

from munshi_apply_native.runtime_resolution_read_v1 import (
    OPEN_STATUSES,
    SUBMISSION_AUTHORITY,
    RuntimeResolutionReadModel,
)


class FakeTask:
    def __init__(
        self,
        *,
        task_id,
        application_id="app-1",
        session_id="session-1",
        status="WAITING_FOR_USER",
        resolution=None,
    ):
        self.task_id = task_id
        self.application_id = application_id
        self.session_id = session_id
        self.status = status
        self._payload = {
            "schema_version": "resolution-task-v1",
            "task_id": task_id,
            "application_id": application_id,
            "session_id": session_id,
            "checkpoint_id": "checkpoint-1",
            "page_id": "page-1",
            "control_id": "control-1",
            "question_id": "portfolio",
            "question": "Portfolio URL",
            "semantic_type": "URL",
            "category": "NORMAL",
            "status": status,
            "risk_level": "LOW",
            "auto_resolvable": False,
            "requires_user": True,
            "grouping_scope": "APPLICATION",
            "group_key": "app-1",
            "source_refs": ["hidden-source", "sensitivity:NORMAL"],
            "evidence_refs": ["hidden-evidence"],
            "attempted_resolvers": ["answer-brain"],
            "reason": "No confirmed answer",
            "resolution": resolution,
            "created_at": "2026-09-09T12:00:00+00:00",
            "updated_at": "2026-09-09T12:00:01+00:00",
        }

    def database_record(self):
        return dict(self._payload)


class FakeQueue:
    def __init__(self, row=None, error=None):
        self.row = row or {
            "job_id": "prepare-job-1",
            "session_id": "session-1",
            "tenant_id": "tenant-a",
            "user_id": "user-a",
            "application_id": "app-1",
            "plan_id": "plan-1",
            "provider": "GREENHOUSE",
            "state": "WAITING_INPUT",
        }
        self.error = error
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.error:
            raise self.error
        return dict(self.row)


class FakeStore:
    def __init__(self, tasks):
        self.rows = list(tasks)
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(dict(kwargs))
        return list(self.rows)


def model(tasks, queue=None):
    obj = object.__new__(RuntimeResolutionReadModel)
    obj.queue = queue or FakeQueue()
    obj.tasks = FakeStore(tasks)
    return obj


def test_exact_session_open_tasks_are_sanitized_and_resolution_value_is_omitted():
    current = FakeTask(task_id="task-current", resolution={"value": "SECRET-ANSWER-MUST-NOT-LEAK"})
    old = FakeTask(task_id="task-old", session_id="session-old")
    resolved = FakeTask(task_id="task-resolved", status="RESOLVED", resolution={"value": "old"})
    view = model([old, resolved, current]).for_prepare_job(
        job_id="prepare-job-1", tenant_id="tenant-a", user_id="user-a"
    )
    assert view["open_task_count"] == 1
    assert view["resolution_values_exposed"] is False
    assert view["submission_authority"] is False
    task = view["resolution_tasks"][0]
    assert task["task_id"] == "task-current"
    assert task["sensitivity_class"] == "NORMAL"
    assert "resolution" not in task
    assert "source_refs" not in task
    assert "evidence_refs" not in task
    assert "attempted_resolvers" not in task
    assert "SECRET-ANSWER-MUST-NOT-LEAK" not in repr(view)


@pytest.mark.parametrize("status", sorted(OPEN_STATUSES))
def test_all_open_states_are_exposed(status):
    view = model([FakeTask(task_id=f"task-{status}", status=status)]).for_prepare_job(
        job_id="prepare-job-1", tenant_id="tenant-a", user_id="user-a"
    )
    assert view["open_task_count"] == 1


def test_terminal_tasks_are_not_exposed():
    rows = [
        FakeTask(task_id="r", status="RESOLVED"),
        FakeTask(task_id="f", status="FAILED"),
        FakeTask(task_id="e", status="EXPIRED"),
    ]
    view = model(rows).for_prepare_job(
        job_id="prepare-job-1", tenant_id="tenant-a", user_id="user-a"
    )
    assert view["resolution_tasks"] == []


def test_owner_boundary_failure_is_not_bypassed():
    obj = model([], queue=FakeQueue(error=PermissionError("another owner")))
    with pytest.raises(PermissionError, match="another owner"):
        obj.for_prepare_job(job_id="prepare-job-1", tenant_id="wrong", user_id="wrong")
    assert obj.tasks.calls == []


def test_application_binding_mismatch_fails_closed():
    with pytest.raises(RuntimeError, match="application binding"):
        model([FakeTask(task_id="bad", application_id="another-app")]).for_prepare_job(
            job_id="prepare-job-1", tenant_id="tenant-a", user_id="user-a"
        )


def test_read_model_never_grants_submission_authority():
    assert SUBMISSION_AUTHORITY is False
