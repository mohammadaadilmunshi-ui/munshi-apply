from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .database import Database, canonical_json

_LIFECYCLE_TYPES = {
    "DETECTED",
    "PREPARED",
    "AUTOPILOT_STARTED",
    "AUTOPILOT_COMPLETED",
    "AUTOPILOT_PAUSED",
    "AUTOPILOT_FAILED",
    "DRAFT_USED",
    "RESUME_USED",
    "RECRUITER_RESPONSE",
    "JOB_SIGNALS_ANALYZED",
}
_OUTCOME_STAGES = {
    "APPLIED",
    "ASSESSMENT",
    "INTERVIEW",
    "OFFER",
    "REJECTED",
    "WITHDRAWN",
}


def _required_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _timestamp(payload: dict[str, Any], key: str, label: str) -> str:
    value = _required_text(payload, key, label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return value


def _optional_label(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string or null")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 200:
        raise ValueError(f"{label} is too long")
    return normalized


def _ensure_application(connection: Any, application_id: str, observed_at: str) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO applications (
            application_id, job_id, status, resume_id, job_signal_score,
            submitted_at, created_at, updated_at
        ) VALUES (?, NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
        """,
        (application_id, observed_at, observed_at),
    )


class ApplicationAnalyticsStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record_event(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            raise ValueError("Application analytics event payload must be an object")
        event_id = _required_text(payload, "eventId", "Analytics eventId")
        application_id = _required_text(payload, "applicationId", "Analytics applicationId")
        event_type = _required_text(payload, "eventType", "Analytics eventType")
        if event_type not in _LIFECYCLE_TYPES:
            raise ValueError("Unsupported application analytics eventType")
        occurred_at = _timestamp(payload, "occurredAt", "Analytics occurredAt")
        source = _required_text(payload, "source", "Analytics source")
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Analytics metadata must be an object")
        metadata_json = canonical_json(metadata)

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_application(connection, application_id, occurred_at)
            existing = connection.execute(
                "SELECT * FROM application_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                same = (
                    existing["application_id"] == application_id
                    and existing["event_type"] == event_type
                    and existing["occurred_at"] == occurred_at
                    and existing["source"] == source
                    and existing["metadata_json"] == metadata_json
                )
                if not same:
                    raise ValueError(
                        "Analytics event id already refers to a different immutable event"
                    )
                return False
            connection.execute(
                """
                INSERT INTO application_events (
                    event_id, application_id, event_type, occurred_at, source, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, application_id, event_type, occurred_at, source, metadata_json),
            )
        return True

    def record_context(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            raise ValueError("Attribution context payload must be an object")
        event_id = _required_text(payload, "eventId", "Attribution eventId")
        application_id = _required_text(payload, "applicationId", "Attribution applicationId")
        captured_at = _timestamp(payload, "capturedAt", "Attribution capturedAt")
        metadata = {
            "jobSource": _optional_label(payload.get("jobSource"), "jobSource"),
            "atsFamily": _optional_label(payload.get("atsFamily"), "atsFamily"),
            "resumeId": _optional_label(payload.get("resumeId"), "resumeId"),
        }
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_application(connection, application_id, captured_at)
            existing = connection.execute(
                "SELECT * FROM application_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            metadata_json = canonical_json(metadata)
            if existing is not None:
                same = (
                    existing["application_id"] == application_id
                    and existing["event_type"] == "ATTRIBUTION_CONTEXT"
                    and existing["occurred_at"] == captured_at
                    and existing["source"] == "extension"
                    and existing["metadata_json"] == metadata_json
                )
                if not same:
                    raise ValueError(
                        "Attribution event id already refers to a different immutable context"
                    )
                return False
            connection.execute(
                """
                INSERT INTO application_events (
                    event_id, application_id, event_type, occurred_at, source, metadata_json
                ) VALUES (?, ?, 'ATTRIBUTION_CONTEXT', ?, 'extension', ?)
                """,
                (event_id, application_id, captured_at, metadata_json),
            )
        return True

    def record_outcome(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            raise ValueError("Application outcome payload must be an object")
        event_id = _required_text(payload, "eventId", "Outcome eventId")
        application_id = _required_text(payload, "applicationId", "Outcome applicationId")
        stage = _required_text(payload, "stage", "Outcome stage")
        if stage not in _OUTCOME_STAGES:
            raise ValueError("Unsupported application outcome stage")
        occurred_at = _timestamp(payload, "occurredAt", "Outcome occurredAt")
        source = _required_text(payload, "source", "Outcome source")

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_application(connection, application_id, occurred_at)
            existing = connection.execute(
                "SELECT * FROM application_outcomes WHERE outcome_event_id = ?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                same = (
                    existing["application_id"] == application_id
                    and existing["stage"] == stage
                    and existing["occurred_at"] == occurred_at
                    and existing["source"] == source
                )
                if not same:
                    raise ValueError(
                        "Outcome event id already refers to a different immutable event"
                    )
                return False
            connection.execute(
                """
                INSERT INTO application_outcomes (
                    outcome_event_id, application_id, stage, occurred_at, source
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, application_id, stage, occurred_at, source),
            )
        return True

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        with self.database.connect() as connection:
            event_rows = connection.execute(
                """
                SELECT event_id, application_id, event_type, occurred_at, source, metadata_json
                FROM application_events
                WHERE event_type = 'ATTRIBUTION_CONTEXT'
                   OR event_type IN (
                     'DETECTED', 'PREPARED', 'AUTOPILOT_STARTED',
                     'AUTOPILOT_COMPLETED', 'AUTOPILOT_PAUSED', 'AUTOPILOT_FAILED',
                     'DRAFT_USED', 'RESUME_USED', 'RECRUITER_RESPONSE',
                     'JOB_SIGNALS_ANALYZED'
                   )
                ORDER BY occurred_at, event_id
                """
            ).fetchall()
            outcome_rows = connection.execute(
                """
                SELECT outcome_event_id, application_id, stage, occurred_at, source
                FROM application_outcomes
                ORDER BY occurred_at, outcome_event_id
                """
            ).fetchall()

        latest_contexts: dict[str, dict[str, Any]] = {}
        lifecycle: list[dict[str, Any]] = []
        for row in event_rows:
            metadata = json.loads(row["metadata_json"])
            if row["event_type"] == "ATTRIBUTION_CONTEXT":
                latest_contexts[row["application_id"]] = {
                    "applicationId": row["application_id"],
                    "capturedAt": row["occurred_at"],
                    "jobSource": metadata.get("jobSource"),
                    "atsFamily": metadata.get("atsFamily"),
                    "resumeId": metadata.get("resumeId"),
                }
                continue
            lifecycle.append(
                {
                    "eventId": row["event_id"],
                    "applicationId": row["application_id"],
                    "eventType": row["event_type"],
                    "occurredAt": row["occurred_at"],
                    "source": row["source"],
                    "metadata": metadata,
                }
            )

        outcomes = [
            {
                "eventId": row["outcome_event_id"],
                "applicationId": row["application_id"],
                "stage": row["stage"],
                "occurredAt": row["occurred_at"],
                "source": row["source"],
            }
            for row in outcome_rows
        ]
        return {
            "contexts": list(latest_contexts.values()),
            "lifecycleEvents": lifecycle,
            "outcomes": outcomes,
        }
