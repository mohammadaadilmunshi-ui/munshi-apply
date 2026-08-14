from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

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

ApplicationState = Literal[
    "JOB_CONTEXT",
    "AUTH",
    "ACCOUNT_CREATE",
    "VERIFY_ACCOUNT",
    "PERSONAL",
    "EDUCATION",
    "EXPERIENCE",
    "RESUME",
    "QUESTIONS",
    "EEO",
    "DISCLOSURES",
    "REVIEW",
    "SUBMISSION",
    "CONFIRMATION",
    "COMPLETE",
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


class ApplicationCheckpointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    checkpoint_id: str = Field(alias="checkpointId", min_length=1, max_length=128)
    application_id: str = Field(alias="applicationId", min_length=1, max_length=128)
    sequence: int = Field(ge=0)
    state: ApplicationState
    page_id: str = Field(alias="pageId", min_length=1, max_length=256)
    page_fingerprint: str = Field(alias="pageFingerprint", min_length=1, max_length=512)
    completed_control_ids: list[str] = Field(alias="completedControlIds")
    pending_control_ids: list[str] = Field(alias="pendingControlIds")
    selected_resume_id: str | None = Field(alias="selectedResumeId", default=None)
    selected_resume_sha256: str | None = Field(alias="selectedResumeSha256", default=None)
    created_at: datetime = Field(alias="createdAt")

    @field_validator("checkpoint_id", "application_id", "page_id", "page_fingerprint")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Checkpoint identifiers must not be blank")
        return stripped

    @field_validator("completed_control_ids", "pending_control_ids")
    @classmethod
    def validate_control_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("Checkpoint control ids must not be blank")
            normalized.append(stripped)
        if len(set(normalized)) != len(normalized):
            raise ValueError("Checkpoint control ids must not contain duplicates")
        return normalized

    @field_validator("selected_resume_id")
    @classmethod
    def normalize_resume_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("selectedResumeId must not be blank")
        return stripped

    @field_validator("selected_resume_sha256")
    @classmethod
    def validate_resume_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) != 64 or any(
            character not in "0123456789abcdef" for character in stripped
        ):
            raise ValueError("selectedResumeSha256 must be a lowercase SHA-256 digest")
        return stripped

    @model_validator(mode="after")
    def validate_consistency(self) -> ApplicationCheckpointPayload:
        if (self.selected_resume_id is None) != (self.selected_resume_sha256 is None):
            raise ValueError("Résumé checkpoint identity and digest must be stored together")
        completed = set(self.completed_control_ids)
        if any(item in completed for item in self.pending_control_ids):
            raise ValueError("Completed and pending checkpoint controls must not overlap")
        return self

    def database_record(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "application_id": self.application_id,
            "sequence": self.sequence,
            "state": self.state,
            "page_id": self.page_id,
            "page_fingerprint": self.page_fingerprint,
            "completed_control_ids": list(self.completed_control_ids),
            "pending_control_ids": list(self.pending_control_ids),
            "selected_resume_id": self.selected_resume_id,
            "selected_resume_sha256": self.selected_resume_sha256,
            "created_at": self.created_at.isoformat(),
        }

    def wire_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


class HealthResponse(BaseModel):
    status: str
    database: str
    migration_count: int
    schema_version: str
    outbox: dict[str, int]
    outbox_worker: str
    n8n_configured: bool
    version: str
