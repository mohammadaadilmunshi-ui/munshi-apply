from __future__ import annotations

from typing import Any

from .account_native_messages import handle_account_message
from .application_store import ApplicationStore
from .database import Database
from .interaction_knowledge_store import InteractionKnowledgeStore
from .models import ResolutionTaskPayload, ResolutionTaskStatus
from .resolution_task_store import ResolutionTaskStore
from .teach_munshi_service import TeachMunshiService

_RESOLUTION_MESSAGE_TYPES = {
    "UPSERT_RESOLUTION_TASK",
    "GET_RESOLUTION_TASK",
    "LIST_RESOLUTION_TASKS",
}
_TEACH_MESSAGE_TYPES = {
    "CAPTURE_TEACH_MUNSHI_LESSON",
    "DRAIN_TEACH_MUNSHI_LESSONS",
    "GET_TEACH_MUNSHI_METRICS",
    "RECORD_INTERACTION_RESOLUTION",
    "GET_INTERACTION_COST_SUMMARY",
}
_RESOLUTION_STATUSES = {
    "PENDING",
    "RESOLVING",
    "WAITING_FOR_USER",
    "RESOLVED",
    "FAILED",
    "EXPIRED",
}


def _payload(message: dict[str, object], label: str) -> dict[str, Any]:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"{label} payload must be an object")
    return payload


def _required_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} requires {key}")
    return value.strip()


def _optional_text(payload: dict[str, Any], key: str, label: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} {key} must be a non-empty string")
    return value.strip()


def _list_filters(
    message: dict[str, object],
) -> tuple[str | None, ResolutionTaskStatus | None, str | None, int]:
    payload = _payload(message, "Resolution task list")
    application_id = _optional_text(payload, "applicationId", "Resolution task list")
    group_key = _optional_text(payload, "groupKey", "Resolution task list")
    status_value = payload.get("status")
    status: ResolutionTaskStatus | None = None
    if status_value is not None:
        if not isinstance(status_value, str) or status_value not in _RESOLUTION_STATUSES:
            raise ValueError("Resolution task list status is invalid")
        status = status_value  # type: ignore[assignment]
    limit_value = payload.get("limit", 200)
    if isinstance(limit_value, bool) or not isinstance(limit_value, int):
        raise ValueError("Resolution task list limit must be an integer")
    if limit_value < 1 or limit_value > 500:
        raise ValueError("Resolution task list limit must be between 1 and 500")
    return application_id, status, group_key, limit_value


def _handle_teach_message(
    message: dict[str, object],
    database: Database,
) -> dict[str, object] | None:
    message_type = message.get("type")
    if message_type not in _TEACH_MESSAGE_TYPES:
        return None

    if message_type == "CAPTURE_TEACH_MUNSHI_LESSON":
        return {
            "ok": True,
            "data": TeachMunshiService(database).capture(message.get("payload")),
        }
    if message_type == "DRAIN_TEACH_MUNSHI_LESSONS":
        payload = message.get("payload")
        limit = 20
        if payload is not None:
            if not isinstance(payload, dict):
                raise ValueError("Teach MUNSHI drain payload must be an object")
            raw_limit = payload.get("limit", 20)
            if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
                raise ValueError("Teach MUNSHI drain limit must be an integer")
            limit = raw_limit
        return {
            "ok": True,
            "data": TeachMunshiService(database).drain(limit=limit),
        }
    if message_type == "GET_TEACH_MUNSHI_METRICS":
        return {"ok": True, "data": TeachMunshiService(database).metrics()}
    if message_type == "RECORD_INTERACTION_RESOLUTION":
        payload = _payload(message, "Interaction resolution")
        created = InteractionKnowledgeStore(database).record_resolution(payload)
        return {"ok": True, "data": {"created": created}}

    payload = message.get("payload")
    since: str | None = None
    if payload is not None:
        if not isinstance(payload, dict):
            raise ValueError("Interaction cost summary payload must be an object")
        since = _optional_text(payload, "since", "Interaction cost summary")
    return {
        "ok": True,
        "data": InteractionKnowledgeStore(database).cost_summary(since=since),
    }


def handle_resolution_task_message(
    message: dict[str, object],
    database: Database,
) -> dict[str, object] | None:
    # This dispatcher is invoked before the legacy native-message switch.
    # ATS account lifecycle/Teach messages use the same seam so account state
    # can advance without introducing another native protocol or any submit authority.
    account_response = handle_account_message(message, database)
    if account_response is not None:
        return account_response

    # Generic Teach MUNSHI remains isolated from password/auth controls. The
    # account-specific Teach router above only accepts secretless semantic actions.
    teach_response = _handle_teach_message(message, database)
    if teach_response is not None:
        return teach_response

    message_type = message.get("type")
    if message_type not in _RESOLUTION_MESSAGE_TYPES:
        return None

    store = ResolutionTaskStore(database)
    if message_type == "UPSERT_RESOLUTION_TASK":
        task = ResolutionTaskPayload.model_validate(message.get("payload"))
        ApplicationStore(database).ensure(task.application_id, task.created_at.isoformat())
        created = store.upsert(task)
        return {
            "ok": True,
            "data": {"created": created, "task": task.wire_payload()},
        }

    if message_type == "GET_RESOLUTION_TASK":
        payload = _payload(message, "Resolution task lookup")
        task_id = _required_text(payload, "taskId", "Resolution task lookup")
        task = store.get(task_id)
        return {
            "ok": True,
            "data": task.wire_payload() if task is not None else None,
        }

    application_id, status, group_key, limit = _list_filters(message)
    tasks = store.list(
        application_id=application_id,
        status=status,
        group_key=group_key,
        limit=limit,
    )
    return {"ok": True, "data": [task.wire_payload() for task in tasks]}
