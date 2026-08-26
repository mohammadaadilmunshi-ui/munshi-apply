from __future__ import annotations

import json
from typing import Any

from .database import Database, canonical_json


class ApplicationCheckpointStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _from_row(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["completed_control_ids"] = json.loads(item.pop("completed_control_ids_json"))["items"]
        item["pending_control_ids"] = json.loads(item.pop("pending_control_ids_json"))["items"]
        return item

    def save(self, checkpoint: dict[str, Any]) -> bool:
        """Insert once, accept an exact retry, and reject divergent sequence reuse."""
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_sequence = connection.execute(
                """
                SELECT * FROM application_checkpoints
                WHERE application_id = ? AND sequence = ?
                """,
                (checkpoint["application_id"], checkpoint["sequence"]),
            ).fetchone()
            if existing_sequence is not None:
                existing = self._from_row(existing_sequence)
                if existing == checkpoint:
                    return False
                raise ValueError("Checkpoint sequence already exists with different content")

            existing_id = connection.execute(
                "SELECT * FROM application_checkpoints WHERE checkpoint_id = ?",
                (checkpoint["checkpoint_id"],),
            ).fetchone()
            if existing_id is not None:
                raise ValueError("Checkpoint id is already bound to different content")

            latest = connection.execute(
                """
                SELECT sequence FROM application_checkpoints
                WHERE application_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (checkpoint["application_id"],),
            ).fetchone()
            if latest is not None and checkpoint["sequence"] <= latest["sequence"]:
                raise ValueError("Checkpoint sequence must advance monotonically")

            connection.execute(
                """
                INSERT INTO application_checkpoints (
                    checkpoint_id, application_id, sequence, state, page_id,
                    page_fingerprint, completed_control_ids_json,
                    pending_control_ids_json, selected_resume_id,
                    selected_resume_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint["checkpoint_id"],
                    checkpoint["application_id"],
                    checkpoint["sequence"],
                    checkpoint["state"],
                    checkpoint["page_id"],
                    checkpoint["page_fingerprint"],
                    canonical_json({"items": checkpoint.get("completed_control_ids", [])}),
                    canonical_json({"items": checkpoint.get("pending_control_ids", [])}),
                    checkpoint.get("selected_resume_id"),
                    checkpoint.get("selected_resume_sha256"),
                    checkpoint["created_at"],
                ),
            )
        return True

    def latest(self, application_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM application_checkpoints
                WHERE application_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (application_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)
