from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FoundationEventType = Literal[
    "APPLICATION_DETECTED",
    "APPLICATION_PREPARED",
    "AUTOPILOT_STARTED",
    "ACCOUNT_REQUIRED",
    "ACCOUNT_CREATED",
    "RESUME_SELECTED",
    "RESUME_UPLOADED",
    "RESUME_VERIFIED",
    "QUESTION_REVIEW_REQUIRED",
    "SECURITY_CHECKPOINT",
    "APPLICATION_SUBMITTED",
    "APPLICATION_CONFIRMED",
    "APPLICATION_COMPLETED",
    "PORTFOLIO_VISIT_OBSERVED",
    "FOLLOWUP_DUE",
    "ASSESSMENT_RECEIVED",
    "INTERVIEW_RECEIVED",
    "REJECTION_RECEIVED",
    "OFFER_RECEIVED",
    "STATUS_CHANGED",
    "LEARNING_EVENT_CREATED",
    "PAGE_DETECTED",
]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    event_type: FoundationEventType
    occurred_at: datetime
    application_id: str | None = None
    source: Literal["munshi-apply"] = "munshi-apply"
    payload: dict[str, Any] = Field(default_factory=dict)

    def database_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "source": self.source,
            "application_id": self.application_id,
            "payload": self.payload,
        }


class HealthResponse(BaseModel):
    status: str
    database: str
    migration_count: int
    schema_version: str
    outbox: dict[str, int]
    outbox_worker: str
    n8n_configured: bool
    version: str
