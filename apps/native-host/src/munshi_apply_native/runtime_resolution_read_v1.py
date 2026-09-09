"""Owner-scoped, read-only runtime NEEDS_INPUT metadata for Hunter.

No stored resolution value, final-review authority, submission authority,
browser action, provider action, or email action crosses this boundary.
"""

from __future__ import annotations

from typing import Any

from .background_prepare_queue import DurablePreparationQueue
from .database import Database
from .resolution_task_store import ResolutionTaskStore

READ_MODEL_VERSION = "munshi-runtime-resolution-read-v1"
OPEN_STATUSES = frozenset({"PENDING", "RESOLVING", "WAITING_FOR_USER"})
SUBMISSION_AUTHORITY = False
_SAFE_FIELDS = (
    "schema_version",
    "task_id",
    "application_id",
    "session_id",
    "checkpoint_id",
    "page_id",
    "control_id",
    "question_id",
    "question",
    "semantic_type",
    "category",
    "sensitivity_class",
    "status",
    "risk_level",
    "auto_resolvable",
    "requires_user",
    "grouping_scope",
    "group_key",
    "reason",
    "created_at",
    "updated_at",
)


def _safe_task(task: Any) -> dict[str, Any]:
    # database_record() intentionally uses stable snake_case field names; the
    # wire payload uses camelCase aliases and is therefore not the read-model
    # contract Hunter consumes.
    payload = task.database_record()
    if not isinstance(payload, dict) or "resolution" not in payload:
        raise RuntimeError("Resolution task payload contract changed")
    sensitivity_refs = [
        str(value).split(":", 1)[1].upper()
        for value in (payload.get("source_refs") or [])
        if str(value).startswith("sensitivity:")
    ]
    sensitivity = sensitivity_refs[0] if len(sensitivity_refs) == 1 else "UNKNOWN"
    if sensitivity not in {"NORMAL", "PROTECTED", "SELF_ID", "CREDENTIAL", "POST_OFFER"}:
        sensitivity = "UNKNOWN"
    result = {key: payload.get(key) for key in _SAFE_FIELDS}
    result["sensitivity_class"] = sensitivity
    result["submission_authority"] = False
    return result


class RuntimeResolutionReadModel:
    def __init__(self, database: Database) -> None:
        self.queue = DurablePreparationQueue(database)
        self.tasks = ResolutionTaskStore(database)

    def for_prepare_job(self, *, job_id: str, tenant_id: str, user_id: str) -> dict[str, Any]:
        job = self.queue.get(job_id=str(job_id), tenant_id=str(tenant_id), user_id=str(user_id))
        application_id = str(job["application_id"])
        session_id = str(job["session_id"])
        candidates = self.tasks.list(application_id=application_id, limit=500)
        safe: list[dict[str, Any]] = []
        for task in candidates:
            if str(task.application_id) != application_id:
                raise RuntimeError("Resolution task application binding changed")
            if str(task.session_id or "") != session_id:
                continue
            if str(task.status) not in OPEN_STATUSES:
                continue
            safe.append(_safe_task(task))
        safe.sort(
            key=lambda row: (
                str(row.get("question_id") or ""),
                str(row.get("task_id") or ""),
            )
        )
        return {
            "version": READ_MODEL_VERSION,
            "job_id": str(job["job_id"]),
            "session_id": session_id,
            "application_id": application_id,
            "plan_id": str(job["plan_id"]),
            "provider": str(job["provider"]),
            "prepare_state": str(job["state"]),
            "resolution_tasks": safe,
            "open_task_count": len(safe),
            "resolution_values_exposed": False,
            "final_review_authority": False,
            "submission_authority": False,
        }
