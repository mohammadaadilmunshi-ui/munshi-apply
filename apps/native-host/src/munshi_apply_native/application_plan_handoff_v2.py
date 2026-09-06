"""Fail-closed Application Plan V2 transport consumer.

Acceptance authenticates, validates, and persists the exact Hunter execution
intent. It deliberately performs no browser action, field fill, resume upload,
credential use, or final submission. `PLAN_ACCEPTED` is an acknowledgement only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .database import Database, canonical_json
from .n8n import verify_signature

TRANSPORT_VERSION = "munshi-application-plan-handoff-v2"
PLAN_VERSION = "munshi-application-plan-v2"
LIVE_HANDOFF_ENV = "MUNSHI_APPLY_LIVE_HANDOFF_ENABLED"
SUPPORTED_PROVIDERS = frozenset(
    {"GREENHOUSE", "LEVER", "ASHBY", "SMARTRECRUITERS", "WORKDAY"}
)


def live_handoff_enabled() -> bool:
    return str(os.getenv(LIVE_HANDOFF_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _plan_digest_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "idempotency_key", "plan_digest", "created_at"}
    }


class ContentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_plan_version: Literal["munshi-application-plan-v2"]
    receiver_min_version: Literal[2]
    receiver_max_version: Literal[2]


class ApplicationPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["munshi-application-plan-handoff-v2"]
    handoff_id: str = Field(min_length=1, max_length=160)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    application_id: str = Field(min_length=1, max_length=240)
    plan_id: str = Field(min_length=1, max_length=240)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1, max_length=64)
    state: Literal["READY_TO_APPLY"]
    content_contract: ContentContract
    plan: dict[str, Any]
    submission_authority: Literal[False]

    @field_validator(
        "handoff_id", "tenant_id", "user_id", "application_id", "plan_id", "provider"
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Application Plan envelope identifiers must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_plan_contract(self) -> "ApplicationPlanEnvelope":
        if self.provider.upper() not in SUPPORTED_PROVIDERS:
            raise ValueError("Application Plan provider is not supported by this contract")
        plan = self.plan
        if plan.get("version") != PLAN_VERSION:
            raise ValueError("Application Plan version is unsupported")
        if plan.get("application_id") != self.application_id:
            raise ValueError("Application Plan application binding does not match envelope")
        embedded_plan_id = plan.get("plan_id")
        if embedded_plan_id is not None and embedded_plan_id != self.plan_id:
            raise ValueError("Application Plan identity does not match envelope")
        if plan.get("expected_state") != "READY_TO_APPLY" or plan.get("executable") is not True:
            raise ValueError("Application Plan is not execution-ready")
        if plan.get("submission_authority") is not False:
            raise ValueError("Application Plan must not carry submission authority")
        provider_policy = plan.get("provider_policy")
        if not isinstance(provider_policy, dict):
            raise ValueError("Application Plan provider policy is missing")
        if str(provider_policy.get("provider") or "").upper() != self.provider.upper():
            raise ValueError("Application Plan provider binding does not match envelope")
        if provider_policy.get("permitted") is not True:
            raise ValueError("Application Plan provider is not permitted")
        if _sha256_json(_plan_digest_payload(plan)) != self.plan_digest:
            raise ValueError("Application Plan digest does not match exact plan content")
        embedded_digest = plan.get("plan_digest")
        if embedded_digest is not None and embedded_digest != self.plan_digest:
            raise ValueError("Embedded Application Plan digest does not match envelope")
        for key, expected in (("tenant_id", self.tenant_id), ("user_id", self.user_id)):
            if key in plan and str(plan.get(key)) != expected:
                raise ValueError(f"Application Plan {key} binding does not match envelope")
        resume = plan.get("resume")
        job = plan.get("job")
        truth = plan.get("candidate_truth_binding")
        if not isinstance(resume, dict) or not isinstance(job, dict) or not isinstance(truth, dict):
            raise ValueError("Application Plan required bindings are missing")
        if not resume.get("artifact_id") or len(str(resume.get("artifact_sha256") or "")) != 64:
            raise ValueError("Application Plan resume artifact binding is incomplete")
        if len(str(job.get("job_snapshot_digest") or "")) != 64:
            raise ValueError("Application Plan job snapshot binding is incomplete")
        if len(str(truth.get("profile_digest") or "")) != 64:
            raise ValueError("Application Plan Candidate Truth binding is incomplete")
        return self


@dataclass(frozen=True)
class PlanHandoffResult:
    accepted: bool
    replayed: bool
    state: str
    handoff_id: str | None = None
    plan_id: str | None = None
    plan_digest: str | None = None
    error: str | None = None


class ApplicationPlanHandoffConsumer:
    def __init__(
        self,
        database: Database,
        *,
        bridge_secret: str,
        max_age_seconds: int = 300,
    ) -> None:
        if not bridge_secret:
            raise ValueError("Application Plan bridge secret is required")
        self.database = database
        self.bridge_secret = bridge_secret
        self.max_age_seconds = max_age_seconds

    def accept(
        self,
        body: bytes,
        headers: dict[str, str],
        *,
        now: int | None = None,
    ) -> PlanHandoffResult:
        if not live_handoff_enabled():
            return PlanHandoffResult(False, False, "REJECTED", error="live handoff disabled")

        normalized = {key.lower(): value for key, value in headers.items()}
        event_id = normalized.get("x-munshi-event-id", "")
        timestamp = normalized.get("x-munshi-timestamp", "")
        digest = normalized.get("x-munshi-content-sha256", "")
        signature = normalized.get("x-munshi-signature", "")
        if not verify_signature(
            event_id=event_id,
            timestamp=timestamp,
            body=body,
            content_sha256=digest,
            signature=signature,
            secret=self.bridge_secret,
            now=now,
            max_age_seconds=self.max_age_seconds,
        ):
            return PlanHandoffResult(False, False, "REJECTED", error="invalid signature")

        try:
            raw = json.loads(body)
            envelope = ApplicationPlanEnvelope.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, ValueError):
            return PlanHandoffResult(False, False, "REJECTED", error="malformed or invalid plan")
        if envelope.handoff_id != event_id:
            return PlanHandoffResult(False, False, "REJECTED", error="event identity mismatch")

        body_sha256 = hashlib.sha256(body).hexdigest()
        plan = dict(envelope.plan)
        resume = dict(plan["resume"])
        job = dict(plan["job"])
        accepted_at = datetime.now(UTC).isoformat()
        # Hunter's plan idempotency key is immutable plan metadata. The handoff
        # id remains the replay identity in signed transport headers.
        idempotency_key = str(plan.get("idempotency_key") or envelope.plan_digest)

        try:
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """SELECT * FROM career_os_application_plans
                       WHERE tenant_id=? AND user_id=? AND idempotency_key=?""",
                    (envelope.tenant_id, envelope.user_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if (
                        str(existing["plan_id"]) != envelope.plan_id
                        or str(existing["plan_digest"]) != envelope.plan_digest
                        or str(existing["body_sha256"]) != body_sha256
                        or str(existing["handoff_id"]) != envelope.handoff_id
                    ):
                        return PlanHandoffResult(
                            False,
                            False,
                            "REJECTED",
                            error="idempotency or replay payload conflict",
                        )
                    return PlanHandoffResult(
                        True,
                        True,
                        "PLAN_ACCEPTED",
                        handoff_id=envelope.handoff_id,
                        plan_id=envelope.plan_id,
                        plan_digest=envelope.plan_digest,
                    )

                replay = connection.execute(
                    "SELECT body_sha256,plan_id FROM career_os_application_plans WHERE handoff_id=?",
                    (envelope.handoff_id,),
                ).fetchone()
                if replay is not None:
                    if str(replay["body_sha256"]) != body_sha256:
                        return PlanHandoffResult(
                            False,
                            False,
                            "REJECTED",
                            error="handoff replay content conflict",
                        )
                    return PlanHandoffResult(
                        True,
                        True,
                        "PLAN_ACCEPTED",
                        handoff_id=envelope.handoff_id,
                        plan_id=str(replay["plan_id"]),
                        plan_digest=envelope.plan_digest,
                    )

                connection.execute(
                    """INSERT INTO career_os_application_plans(
                           plan_id,handoff_id,tenant_id,user_id,application_id,job_id,
                           provider,plan_version,plan_digest,job_snapshot_sha256,
                           resume_artifact_id,resume_artifact_sha256,body_sha256,
                           idempotency_key,plan_json,acceptance_state,accepted_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PLAN_ACCEPTED',?)""",
                    (
                        envelope.plan_id,
                        envelope.handoff_id,
                        envelope.tenant_id,
                        envelope.user_id,
                        envelope.application_id,
                        str(job["id"]),
                        envelope.provider.upper(),
                        PLAN_VERSION,
                        envelope.plan_digest,
                        str(job["job_snapshot_digest"]),
                        str(resume["artifact_id"]),
                        str(resume["artifact_sha256"]),
                        body_sha256,
                        idempotency_key,
                        canonical_json(plan),
                        accepted_at,
                    ),
                )
        except sqlite3.IntegrityError:
            return PlanHandoffResult(False, False, "REJECTED", error="plan identity conflict")

        return PlanHandoffResult(
            True,
            False,
            "PLAN_ACCEPTED",
            handoff_id=envelope.handoff_id,
            plan_id=envelope.plan_id,
            plan_digest=envelope.plan_digest,
        )
