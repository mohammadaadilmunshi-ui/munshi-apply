from __future__ import annotations

import json
from typing import Any

from .database import Database, canonical_json
from .models import ResolutionTaskPayload, ResolutionTaskStatus

_TERMINAL_STATUSES = {"RESOLVED", "FAILED", "EXPIRED"}
_ALLOWED_TRANSITIONS: dict[ResolutionTaskStatus, set[ResolutionTaskStatus]] = {
    "PENDING": {
        "PENDING",
        "RESOLVING",
        "WAITING_FOR_USER",
        "RESOLVED",
        "FAILED",
        "EXPIRED",
    },
    "RESOLVING": {
        "RESOLVING",
        "WAITING_FOR_USER",
        "RESOLVED",
        "FAILED",
        "EXPIRED",
    },
    "WAITING_FOR_USER": {
        "WAITING_FOR_USER",
        "RESOLVING",
        "RESOLVED",
        "FAILED",
        "EXPIRED",
    },
    "RESOLVED": {"RESOLVED"},
    "FAILED": {"FAILED"},
    "EXPIRED": {"EXPIRED"},
}


def _json_list(value: list[str]) -> str:
    return canonical_json(value)


def _payload_identity(task: ResolutionTaskPayload) -> tuple[object, ...]:
    return (
        task.schema_version,
        task.application_id,
        task.session_id,
        task.checkpoint_id,
        task.page_id,
        task.control_id,
        task.question_id,
        task.question,
        task.semantic_type,
        task.category,
        task.risk_level,
        task.auto_resolvable,
        task.grouping_scope,
        task.group_key,
        tuple(task.source_refs),
        task.created_at,
    )


def _same_payload(left: ResolutionTaskPayload, right: ResolutionTaskPayload) -> bool:
    return canonical_json(left.wire_payload()) == canonical_json(right.wire_payload())


def _row_to_payload(row: Any) -> ResolutionTaskPayload:
    resolution = json.loads(row["resolution_json"]) if row["resolution_json"] else None
    return ResolutionTaskPayload.model_validate(
        {
            "schema_version": row["schema_version"],
            "task_id": row["task_id"],
            "application_id": row["application_id"],
            "session_id": row["session_id"],
            "checkpoint_id": row["checkpoint_id"],
            "page_id": row["page_id"],
            "control_id": row["control_id"],
            "question_id": row["question_id"],
            "question": row["question"],
            "semantic_type": row["semantic_type"],
            "category": row["category"],
            "status": row["status"],
            "risk_level": row["risk_level"],
            "auto_resolvable": bool(row["auto_resolvable"]),
            "requires_user": bool(row["requires_user"]),
            "grouping_scope": row["grouping_scope"],
            "group_key": row["group_key"],
            "source_refs": json.loads(row["source_refs_json"]),
            "evidence_refs": json.loads(row["evidence_refs_json"]),
            "attempted_resolvers": json.loads(row["attempted_resolvers_json"]),
            "reason": row["reason"],
            "resolution": resolution,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


class ResolutionTaskStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, task: ResolutionTaskPayload) -> bool:
        record = task.database_record()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = connection.execute(
                "SELECT * FROM resolution_tasks WHERE task_id = ?",
                (task.task_id,),
            ).fetchone()
            if existing_row is None:
                connection.execute(
                    """
                    INSERT INTO resolution_tasks (
                        task_id, schema_version, application_id, session_id,
                        checkpoint_id, page_id, control_id, question_id, question,
                        semantic_type, category, status, risk_level, auto_resolvable,
                        requires_user, grouping_scope, group_key, source_refs_json,
                        evidence_refs_json, attempted_resolvers_json, reason,
                        resolution_json, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        record["task_id"],
                        record["schema_version"],
                        record["application_id"],
                        record["session_id"],
                        record["checkpoint_id"],
                        record["page_id"],
                        record["control_id"],
                        record["question_id"],
                        record["question"],
                        record["semantic_type"],
                        record["category"],
                        record["status"],
                        record["risk_level"],
                        int(record["auto_resolvable"]),
                        int(record["requires_user"]),
                        record["grouping_scope"],
                        record["group_key"],
                        _json_list(record["source_refs"]),
                        _json_list(record["evidence_refs"]),
                        _json_list(record["attempted_resolvers"]),
                        record["reason"],
                        canonical_json(record["resolution"])
                        if record["resolution"] is not None
                        else None,
                        record["created_at"],
                        record["updated_at"],
                    ),
                )
                return True

            existing = _row_to_payload(existing_row)
            if _same_payload(existing, task):
                return False
            if _payload_identity(existing) != _payload_identity(task):
                raise ValueError("Resolution task immutable identity cannot change")
            if existing.status in _TERMINAL_STATUSES:
                raise ValueError("Terminal resolution tasks cannot be modified")
            if task.status not in _ALLOWED_TRANSITIONS[existing.status]:
                raise ValueError(
                    f"Resolution task status cannot move from {existing.status} to {task.status}"
                )
            if task.updated_at < existing.updated_at:
                raise ValueError("Resolution task updatedAt must advance monotonically")
            if task.updated_at == existing.updated_at:
                raise ValueError(
                    "Resolution task content cannot change without advancing updatedAt"
                )

            connection.execute(
                """
                UPDATE resolution_tasks
                SET status = ?, requires_user = ?, evidence_refs_json = ?,
                    attempted_resolvers_json = ?, reason = ?, resolution_json = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    record["status"],
                    int(record["requires_user"]),
                    _json_list(record["evidence_refs"]),
                    _json_list(record["attempted_resolvers"]),
                    record["reason"],
                    canonical_json(record["resolution"])
                    if record["resolution"] is not None
                    else None,
                    record["updated_at"],
                    task.task_id,
                ),
            )
        return False

    def get(self, task_id: str) -> ResolutionTaskPayload | None:
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("Resolution taskId is required")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM resolution_tasks WHERE task_id = ?",
                (normalized_task_id,),
            ).fetchone()
        return _row_to_payload(row) if row is not None else None

    def list(
        self,
        *,
        application_id: str | None = None,
        status: ResolutionTaskStatus | None = None,
        group_key: str | None = None,
        limit: int = 200,
    ) -> list[ResolutionTaskPayload]:
        if limit < 1 or limit > 500:
            raise ValueError("Resolution task list limit must be between 1 and 500")
        clauses: list[str] = []
        parameters: list[object] = []
        if application_id is not None:
            normalized_application_id = application_id.strip()
            if not normalized_application_id:
                raise ValueError("Resolution task applicationId must not be blank")
            clauses.append("application_id = ?")
            parameters.append(normalized_application_id)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        if group_key is not None:
            normalized_group_key = group_key.strip()
            if not normalized_group_key:
                raise ValueError("Resolution task groupKey must not be blank")
            clauses.append("group_key = ?")
            parameters.append(normalized_group_key)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM resolution_tasks
                {where_clause}
                ORDER BY updated_at DESC, task_id
                LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()
        return [_row_to_payload(row) for row in rows]
