"""Fail-closed, local-only consumer for Career OS preparation handoffs.

Accepting a package is deliberately not an application submission.  This
module has no HTTP client, browser-control, credential, or provider code.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .database import Database, canonical_json
from .n8n import verify_signature

SUPPORTED_PROVIDERS = frozenset({"greenhouse", "lever", "ashby", "smartrecruiters", "workday"})
HandoffState = Literal["PREPARED", "NEEDS_INPUT", "READY_TO_APPLY"]


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: str = Field(min_length=1, max_length=64)


class RequiredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str = Field(min_length=1, max_length=256)
    status: Literal["RESOLVED", "UNRESOLVED"]
    value_reference: str | None = Field(default=None, max_length=256)

    @field_validator("value_reference")
    @classmethod
    def no_blank_reference(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("value_reference must not be blank")
        return value


class PreparationPackage(BaseModel):
    """Tenant-bound contract sent by Hunter to the local Apply companion."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    tenant_id: str = Field(min_length=1, max_length=128)
    package_id: str = Field(min_length=1, max_length=128)
    package_version: int = Field(ge=1)
    job_id: str = Field(min_length=1, max_length=128)
    application_identity: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=1, max_length=64)
    state: HandoffState
    idempotency_key: str = Field(min_length=16, max_length=256)
    artifact_references: list[ArtifactReference] = Field(default_factory=list)
    required_answers: list[RequiredAnswer] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)

    @field_validator("tenant_id", "package_id", "job_id", "application_identity", "provider", "idempotency_key")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifiers must not be blank")
        return value


@dataclass(frozen=True)
class HandoffResult:
    accepted: bool
    replayed: bool
    state: str
    provider_supported: bool
    handoff_id: str | None = None
    error: str | None = None


class CareerOSHandoffConsumer:
    """Verifies signed packages and persists an idempotent audit handoff."""

    def __init__(self, database: Database, *, bridge_secret: str, max_age_seconds: int = 300) -> None:
        if not bridge_secret:
            raise ValueError("Career OS bridge secret is required")
        self.database = database
        self.bridge_secret = bridge_secret
        self.max_age_seconds = max_age_seconds

    def accept(self, body: bytes, headers: dict[str, str], *, now: int | None = None) -> HandoffResult:
        normalized = {key.lower(): value for key, value in headers.items()}
        event_id = normalized.get("x-munshi-event-id", "")
        timestamp = normalized.get("x-munshi-timestamp", "")
        digest = normalized.get("x-munshi-content-sha256", "")
        signature = normalized.get("x-munshi-signature", "")
        if not verify_signature(event_id=event_id, timestamp=timestamp, body=body,
                                content_sha256=digest, signature=signature,
                                secret=self.bridge_secret, now=now,
                                max_age_seconds=self.max_age_seconds):
            return HandoffResult(False, False, "REJECTED", False, error="invalid signature")
        try:
            raw = json.loads(body)
            package = PreparationPackage.model_validate(raw)
        except (json.JSONDecodeError, ValidationError):
            return HandoffResult(False, False, "REJECTED", False, error="malformed package")
        package_json = canonical_json(package.model_dump(mode="json"))
        actual_digest = hashlib.sha256(body).hexdigest()
        provider_supported = package.provider.lower() in SUPPORTED_PROVIDERS
        accepted_state = package.state if provider_supported else "NEEDS_INPUT"
        handoff_id = f"handoff-{uuid.uuid4()}"
        received_at = datetime.now(UTC).isoformat()
        try:
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT handoff_id, body_sha256, handoff_state FROM career_os_preparation_handoffs "
                    "WHERE tenant_id = ? AND idempotency_key = ?",
                    (package.tenant_id, package.idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["body_sha256"] != actual_digest:
                        return HandoffResult(False, False, "REJECTED", provider_supported,
                                             error="idempotency key payload conflict")
                    return HandoffResult(True, True, existing["handoff_state"], provider_supported,
                                         handoff_id=existing["handoff_id"])
                connection.execute(
                    """INSERT INTO career_os_preparation_handoffs (
                        handoff_id, tenant_id, package_id, package_version, job_id,
                        application_identity, provider, handoff_state, idempotency_key,
                        body_sha256, package_json, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (handoff_id, package.tenant_id, package.package_id, package.package_version,
                     package.job_id, package.application_identity, package.provider, accepted_state,
                     package.idempotency_key, actual_digest, package_json, received_at),
                )
        except sqlite3.IntegrityError:
            return HandoffResult(False, False, "REJECTED", provider_supported,
                                 error="package version conflict")
        # Handoff acceptance is expressly not a submit receipt or provider action.
        return HandoffResult(True, False, "HANDOFF_ACCEPTED", provider_supported, handoff_id=handoff_id)
