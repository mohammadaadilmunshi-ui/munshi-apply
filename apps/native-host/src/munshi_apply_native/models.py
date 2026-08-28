from __future__ import annotations

from datetime import UTC, datetime
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

ResolutionTaskCategory = Literal[
    "MISSING_FACT",
    "AMBIGUOUS_QUESTION",
    "LOW_CONFIDENCE",
    "AUTHENTICATION",
    "EMAIL_VERIFICATION",
    "INTERACTION_FAILURE",
    "DOCUMENT_REQUIRED",
    "LEGAL_CONFIRMATION",
    "CAPTCHA",
    "EXTERNAL_ACTION",
    "TEMPORARY_FAILURE",
    "BLOCKING_CONFLICT",
]

ResolutionTaskStatus = Literal[
    "PENDING",
    "RESOLVING",
    "WAITING_FOR_USER",
    "RESOLVED",
    "FAILED",
    "EXPIRED",
]

ResolutionRiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
ResolutionGroupingScope = Literal["NONE", "EXACT_QUESTION", "SEMANTIC"]
ResolverStage = Literal[
    "CURRENT_SESSION",
    "MASTER_PROFILE",
    "EVIDENCE_GRAPH",
    "APPROVED_ANSWER_MEMORY",
    "SCOPED_MEMORY",
    "DETERMINISTIC_DERIVATION",
    "GROUNDED_AI",
    "EXTERNAL_RESOLVER",
    "USER_POLICY",
    "USER",
]


def _wire_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
        payload = self.model_dump(mode="json", by_alias=True)
        payload["createdAt"] = _wire_datetime(self.created_at)
        return payload


class ResolutionTaskResolutionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    value: Any
    source: ResolverStage
    evidence_refs: list[str] = Field(alias="evidenceRefs", default_factory=list)
    approved_by_user: bool = Field(alias="approvedByUser")
    resolved_at: datetime = Field(alias="resolvedAt")

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Resolution evidence refs must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Resolution evidence refs must not contain duplicates")
        return normalized


class ResolutionTaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal[1] = Field(alias="schemaVersion")
    task_id: str = Field(alias="taskId", min_length=1, max_length=128)
    application_id: str = Field(alias="applicationId", min_length=1, max_length=128)
    session_id: str | None = Field(alias="sessionId", default=None, max_length=128)
    checkpoint_id: str | None = Field(alias="checkpointId", default=None, max_length=128)
    page_id: str | None = Field(alias="pageId", default=None, max_length=256)
    control_id: str | None = Field(alias="controlId", default=None, max_length=512)
    question_id: str | None = Field(alias="questionId", default=None, max_length=128)
    question: str | None = Field(default=None, max_length=2_000)
    semantic_type: str | None = Field(alias="semanticType", default=None, max_length=128)
    category: ResolutionTaskCategory
    status: ResolutionTaskStatus
    risk_level: ResolutionRiskLevel = Field(alias="riskLevel")
    auto_resolvable: bool = Field(alias="autoResolvable")
    requires_user: bool = Field(alias="requiresUser")
    grouping_scope: ResolutionGroupingScope = Field(alias="groupingScope")
    group_key: str | None = Field(alias="groupKey", default=None, max_length=2_128)
    source_refs: list[str] = Field(alias="sourceRefs", default_factory=list)
    evidence_refs: list[str] = Field(alias="evidenceRefs", default_factory=list)
    attempted_resolvers: list[ResolverStage] = Field(
        alias="attemptedResolvers", default_factory=list
    )
    reason: str = Field(min_length=1, max_length=4_000)
    resolution: ResolutionTaskResolutionPayload | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("task_id", "application_id", "reason")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Resolution task required text must not be blank")
        return stripped

    @field_validator(
        "session_id",
        "checkpoint_id",
        "page_id",
        "control_id",
        "question_id",
        "question",
        "semantic_type",
        "group_key",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("source_refs", "evidence_refs")
    @classmethod
    def validate_refs(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Resolution task refs must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Resolution task refs must not contain duplicates")
        return normalized

    @field_validator("attempted_resolvers")
    @classmethod
    def validate_resolver_attempts(cls, value: list[ResolverStage]) -> list[ResolverStage]:
        if len(set(value)) != len(value):
            raise ValueError("Attempted resolvers must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_consistency(self) -> ResolutionTaskPayload:
        if self.updated_at < self.created_at:
            raise ValueError("Resolution task updatedAt cannot precede createdAt")
        if self.grouping_scope == "NONE" and self.group_key is not None:
            raise ValueError("Ungrouped resolution tasks cannot have a groupKey")
        if self.grouping_scope != "NONE" and self.group_key is None:
            raise ValueError("Grouped resolution tasks require a groupKey")
        if self.status == "RESOLVED" and self.resolution is None:
            raise ValueError("Resolved tasks require resolution details")
        if self.status != "RESOLVED" and self.resolution is not None:
            raise ValueError("Non-resolved tasks cannot contain resolution details")
        if self.status == "WAITING_FOR_USER" and not self.requires_user:
            raise ValueError("Tasks waiting for the user must set requiresUser")
        if self.risk_level == "HIGH" and "GROUNDED_AI" in self.attempted_resolvers:
            raise ValueError("High-risk resolution tasks cannot attempt grounded AI")
        if (
            self.resolution is not None
            and self.risk_level == "HIGH"
            and self.resolution.source == "GROUNDED_AI"
        ):
            raise ValueError("High-risk resolution tasks cannot be resolved by grounded AI")
        if self.category == "CAPTCHA":
            if self.grouping_scope != "NONE":
                raise ValueError("CAPTCHA tasks cannot be grouped")
            if self.auto_resolvable or not self.requires_user:
                raise ValueError("CAPTCHA tasks must require direct user resolution")
        if self.category in {"LEGAL_CONFIRMATION", "BLOCKING_CONFLICT"}:
            if self.auto_resolvable:
                raise ValueError("Legal and blocking tasks cannot be auto-resolvable")
            if self.resolution is not None and not (
                self.resolution.source == "USER" or self.resolution.approved_by_user
            ):
                raise ValueError("Legal and blocking resolutions require user approval")
        return self

    def database_record(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "schema_version": self.schema_version,
            "application_id": self.application_id,
            "session_id": self.session_id,
            "checkpoint_id": self.checkpoint_id,
            "page_id": self.page_id,
            "control_id": self.control_id,
            "question_id": self.question_id,
            "question": self.question,
            "semantic_type": self.semantic_type,
            "category": self.category,
            "status": self.status,
            "risk_level": self.risk_level,
            "auto_resolvable": self.auto_resolvable,
            "requires_user": self.requires_user,
            "grouping_scope": self.grouping_scope,
            "group_key": self.group_key,
            "source_refs": list(self.source_refs),
            "evidence_refs": list(self.evidence_refs),
            "attempted_resolvers": list(self.attempted_resolvers),
            "reason": self.reason,
            "resolution": (
                self.resolution.model_dump(mode="json", by_alias=True)
                if self.resolution is not None
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def wire_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True)
        payload["createdAt"] = _wire_datetime(self.created_at)
        payload["updatedAt"] = _wire_datetime(self.updated_at)
        if self.resolution is not None:
            resolution = dict(payload["resolution"])
            resolution["resolvedAt"] = _wire_datetime(self.resolution.resolved_at)
            payload["resolution"] = resolution
        return payload


class HealthResponse(BaseModel):
    status: str
    database: str
    migration_count: int
    schema_version: str
    outbox: dict[str, int]
    outbox_worker: str
    n8n_configured: bool
    version: str
