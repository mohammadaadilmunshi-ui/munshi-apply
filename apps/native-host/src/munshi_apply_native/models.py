from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventSource = Literal["EXTENSION", "NATIVE_HOST", "USER", "N8N"]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId", min_length=1)
    event_type: str = Field(alias="eventType", min_length=1)
    occurred_at: datetime = Field(alias="occurredAt")
    source: EventSource
    application_id: str | None = Field(default=None, alias="applicationId")
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: Literal[1] = Field(alias="schemaVersion")

    def database_record(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
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
    n8n_configured: bool
    version: str
