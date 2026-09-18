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
from .execution_policy import prepare_permissions
from .n8n import verify_signature

TRANSPORT_VERSION = "munshi-application-plan-handoff-v2"
SUPERSESSION_TRANSPORT_VERSION = "munshi-application-plan-handoff-v3"
SUPERSESSION_VERSION = "munshi-application-plan-supersession-v1"
PLAN_VERSION = "munshi-application-plan-v2"
LIVE_HANDOFF_ENV = "MUNSHI_APPLY_LIVE_HANDOFF_ENABLED"
RUNTIME_SUPERSESSION_ENV = "MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED"
SUPPORTED_PROVIDERS = frozenset({"GREENHOUSE", "LEVER", "ASHBY", "SMARTRECRUITERS", "WORKDAY", "AGILE_ATS"})


def live_handoff_enabled() -> bool:
    return str(os.getenv(LIVE_HANDOFF_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def runtime_supersession_enabled() -> bool:
    return str(os.getenv(RUNTIME_SUPERSESSION_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
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
    receiver_min_version: Literal[2, 3]
    receiver_max_version: Literal[2, 3]


class RuntimeQuestionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_key: str = Field(min_length=1, max_length=160)
    control_id: str = Field(min_length=1, max_length=512)
    question: str = Field(min_length=1, max_length=2000)
    semantic_type: str = Field(min_length=1, max_length=128)
    sensitivity_class: Literal["NORMAL"]


class PlanSupersession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["munshi-application-plan-supersession-v1"]
    prior_plan_id: str = Field(min_length=1, max_length=240)
    prior_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    replacement_plan_id: str = Field(min_length=1, max_length=240)
    replacement_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str = Field(min_length=1, max_length=240)
    checkpoint_id: str = Field(min_length=1, max_length=240)
    browser_form_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    unresolved_questions: list[RuntimeQuestionBinding] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_question_identity(self) -> PlanSupersession:
        keys = [item.question_key for item in self.unresolved_questions]
        controls = [item.control_id for item in self.unresolved_questions]
        if len(keys) != len(set(keys)) or len(controls) != len(set(controls)):
            raise ValueError(
                "Plan supersession questions require unique question and control identities"
            )
        if self.prior_plan_id == self.replacement_plan_id:
            raise ValueError("Plan supersession requires a distinct replacement plan")
        return self


class ApplicationPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[
        "munshi-application-plan-handoff-v2",
        "munshi-application-plan-handoff-v3",
    ]
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
    supersession: PlanSupersession | None = None

    @field_validator("handoff_id", "tenant_id", "user_id", "application_id", "plan_id", "provider")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Application Plan envelope identifiers must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_plan_contract(self) -> ApplicationPlanEnvelope:
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
        prepare_permissions(plan)
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
        cover_letter = plan.get("cover_letter")
        if cover_letter is not None:
            if not isinstance(cover_letter, dict):
                raise ValueError("Application Plan cover-letter binding is invalid")
            if (
                not cover_letter.get("artifact_id")
                or not cover_letter.get("artifact_reference")
                or len(str(cover_letter.get("artifact_sha256") or "")) != 64
                or cover_letter.get("submission_authority") is not False
            ):
                raise ValueError("Application Plan cover-letter artifact binding is incomplete")
            permissions = plan.get("permissions")
            if (
                not isinstance(permissions, dict)
                or permissions.get("cover_letter_upload") is not True
            ):
                raise ValueError("Application Plan cover-letter upload permission is required")
        if len(str(job.get("job_snapshot_digest") or "")) != 64:
            raise ValueError("Application Plan job snapshot binding is incomplete")
        if len(str(truth.get("profile_digest") or "")) != 64:
            raise ValueError("Application Plan Candidate Truth binding is incomplete")
        if self.version == TRANSPORT_VERSION:
            if (
                self.supersession is not None
                or self.content_contract.receiver_min_version != 2
                or self.content_contract.receiver_max_version != 2
            ):
                raise ValueError("V2 Application Plan handoff contract is invalid")
        else:
            if (
                self.supersession is None
                or self.content_contract.receiver_min_version != 3
                or self.content_contract.receiver_max_version != 3
            ):
                raise ValueError("V3 Application Plan supersession contract is invalid")
            if (
                self.supersession.replacement_plan_id != self.plan_id
                or self.supersession.replacement_plan_digest != self.plan_digest
            ):
                raise ValueError(
                    "Plan supersession replacement identity does not match envelope"
                )
        return self


@dataclass(frozen=True)
class PlanHandoffResult:
    accepted: bool
    replayed: bool
    state: str
    handoff_id: str | None = None
    plan_id: str | None = None
    plan_digest: str | None = None
    resumed_session_id: str | None = None
    preparation_job_id: str | None = None
    error: str | None = None


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _same_plan_binding(
    prior_plan: dict[str, Any], replacement_plan: dict[str, Any], key: str
) -> bool:
    return canonical_json({"value": prior_plan.get(key)}) == canonical_json(
        {"value": replacement_plan.get(key)}
    )


def _supersession_target_locked(
    connection: sqlite3.Connection,
    envelope: ApplicationPlanEnvelope,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    supersession = envelope.supersession
    if supersession is None:
        return None
    prior = connection.execute(
        """SELECT * FROM career_os_application_plans
           WHERE plan_id=? AND tenant_id=? AND user_id=?""",
        (supersession.prior_plan_id, envelope.tenant_id, envelope.user_id),
    ).fetchone()
    if prior is None:
        raise ValueError("Superseded Application Plan was not accepted for this owner")
    prior = dict(prior)
    if (
        str(prior["plan_digest"]) != supersession.prior_plan_digest
        or str(prior["application_id"]) != envelope.application_id
        or str(prior["provider"]).upper() != envelope.provider.upper()
        or str(prior["acceptance_state"]) != "PLAN_ACCEPTED"
    ):
        raise ValueError("Superseded Application Plan binding is invalid")

    replacement_plan = dict(envelope.plan)
    prior_plan = json.loads(str(prior["plan_json"]))
    for key in (
        "job",
        "candidate_truth_binding",
        "resume",
        "cover_letter",
        "permissions",
        "provider_policy",
    ):
        if not _same_plan_binding(prior_plan, replacement_plan, key):
            raise ValueError(
                "Replacement Application Plan changed checkpoint-bound preparation inputs"
            )

    session = connection.execute(
        """SELECT * FROM complete_application_sessions
           WHERE session_id=? AND application_id=? AND plan_id=?""",
        (
            supersession.session_id,
            envelope.application_id,
            supersession.prior_plan_id,
        ),
    ).fetchone()
    if session is None:
        raise ValueError(
            "Runtime plan supersession does not match the waiting execution session"
        )
    session = dict(session)
    if (
        str(session["state"]) != "NEEDS_INPUT"
        or str(session["provider"]).upper() != envelope.provider.upper()
        or str(session["checkpoint_id"] or "") != supersession.checkpoint_id
        or str(session["browser_form_digest"] or "") != supersession.browser_form_digest
    ):
        raise ValueError("Runtime plan supersession browser checkpoint is stale")

    prepare_job = connection.execute(
        """SELECT * FROM complete_application_prepare_jobs
           WHERE session_id=? AND tenant_id=? AND user_id=?""",
        (supersession.session_id, envelope.tenant_id, envelope.user_id),
    ).fetchone()
    if prepare_job is None:
        raise ValueError("Runtime plan supersession has no durable preparation job")
    prepare_job = dict(prepare_job)
    if (
        str(prepare_job["state"]) != "WAITING_INPUT"
        or str(prepare_job["plan_id"]) != supersession.prior_plan_id
        or str(prepare_job["application_id"]) != envelope.application_id
        or str(prepare_job["provider"]).upper() != envelope.provider.upper()
        or prepare_job["cancel_requested_at"] is not None
    ):
        raise ValueError("Runtime plan supersession preparation job is not safely resumable")

    review_or_submit_queries = (
        "SELECT COUNT(*) FROM final_application_reviews WHERE session_id=?",
        "SELECT COUNT(*) FROM final_submit_commands WHERE session_id=?",
        "SELECT COUNT(*) FROM application_submission_receipts WHERE session_id=?",
    )
    for query in review_or_submit_queries:
        count = connection.execute(
            query,
            (supersession.session_id,),
        ).fetchone()[0]
        if int(count) != 0:
            raise ValueError(
                "Runtime plan supersession cannot replace a reviewed or submitted session"
            )

    tasks = connection.execute(
        """SELECT task_id,control_id,question,semantic_type,group_key,risk_level
           FROM resolution_tasks
           WHERE session_id=? AND checkpoint_id=? AND status='WAITING_FOR_USER'""",
        (supersession.session_id, supersession.checkpoint_id),
    ).fetchall()
    stored = {
        str(row["group_key"] or row["control_id"] or row["task_id"]): dict(row)
        for row in tasks
    }
    expected = {item.question_key: item for item in supersession.unresolved_questions}
    if set(stored) != set(expected):
        raise ValueError(
            "Runtime plan supersession question set does not match Apply NEEDS_INPUT"
        )
    for key, question in expected.items():
        task = stored[key]
        if (
            str(task["control_id"] or "") != question.control_id
            or _normalized_text(task["question"]) != question.question
            or _normalized_text(task["semantic_type"]) != question.semantic_type
            or str(task["risk_level"]).upper() == "HIGH"
        ):
            raise ValueError(
                "Runtime plan supersession question evidence does not match Apply"
            )
    return session, prepare_job


def _commit_supersession_locked(
    connection: sqlite3.Connection,
    *,
    envelope: ApplicationPlanEnvelope,
    session: dict[str, Any],
    prepare_job: dict[str, Any],
    accepted_at: str,
) -> tuple[str, str]:
    _ = session
    supersession = envelope.supersession
    assert supersession is not None
    connection.execute(
        """INSERT INTO career_os_application_plan_supersessions(
               replacement_plan_id,prior_plan_id,tenant_id,user_id,application_id,
               session_id,prepare_job_id,prior_plan_digest,replacement_plan_digest,
               resolution_digest,browser_form_digest,checkpoint_id,accepted_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            envelope.plan_id,
            supersession.prior_plan_id,
            envelope.tenant_id,
            envelope.user_id,
            envelope.application_id,
            supersession.session_id,
            str(prepare_job["job_id"]),
            supersession.prior_plan_digest,
            supersession.replacement_plan_digest,
            supersession.resolution_digest,
            supersession.browser_form_digest,
            supersession.checkpoint_id,
            accepted_at,
        ),
    )
    updated_session = connection.execute(
        """UPDATE complete_application_sessions
           SET plan_id=?,state_version=state_version+1,updated_at=?
           WHERE session_id=? AND application_id=? AND plan_id=?
             AND state='NEEDS_INPUT' AND checkpoint_id=?
             AND browser_form_digest=?""",
        (
            envelope.plan_id,
            accepted_at,
            supersession.session_id,
            envelope.application_id,
            supersession.prior_plan_id,
            supersession.checkpoint_id,
            supersession.browser_form_digest,
        ),
    )
    if updated_session.rowcount != 1:
        raise RuntimeError("Execution session plan rebind lost its atomic guard")
    updated_job = connection.execute(
        """UPDATE complete_application_prepare_jobs
           SET plan_id=?,state='QUEUED',available_at=?,last_error=NULL,
               finished_at=NULL,updated_at=?
           WHERE job_id=? AND session_id=? AND plan_id=?
             AND state='WAITING_INPUT' AND cancel_requested_at IS NULL""",
        (
            envelope.plan_id,
            accepted_at,
            accepted_at,
            prepare_job["job_id"],
            supersession.session_id,
            supersession.prior_plan_id,
        ),
    )
    if updated_job.rowcount != 1:
        raise RuntimeError("Preparation job plan rebind lost its atomic guard")
    connection.execute(
        """UPDATE resolution_tasks
           SET status='EXPIRED',updated_at=?
           WHERE session_id=? AND checkpoint_id=? AND status='WAITING_FOR_USER'""",
        (accepted_at, supersession.session_id, supersession.checkpoint_id),
    )
    replay_identity = f"{supersession.session_id}:plan-superseded:{envelope.plan_id}"
    event_id = "plan-rebind-" + hashlib.sha256(
        replay_identity.encode("utf-8")
    ).hexdigest()[:32]
    connection.execute(
        """INSERT INTO complete_application_execution_events(
               event_id,application_id,plan_id,session_id,provider,event_type,
               replay_identity,evidence_json,checkpoint_json,occurred_at
           ) VALUES (?,?,?,?,?,'PLAN_SUPERSEDED',?,?,NULL,?)""",
        (
            event_id,
            envelope.application_id,
            envelope.plan_id,
            supersession.session_id,
            envelope.provider.upper(),
            replay_identity,
            canonical_json(
                {
                    "prior_plan_id": supersession.prior_plan_id,
                    "prior_plan_digest": supersession.prior_plan_digest,
                    "replacement_plan_id": envelope.plan_id,
                    "replacement_plan_digest": envelope.plan_digest,
                    "resolution_digest": supersession.resolution_digest,
                    "submission_authority": False,
                }
            ),
            accepted_at,
        ),
    )
    return supersession.session_id, str(prepare_job["job_id"])


def _supersession_replay_locked(
    connection: sqlite3.Connection,
    envelope: ApplicationPlanEnvelope,
) -> tuple[str, str] | None:
    supersession = envelope.supersession
    if supersession is None:
        return None
    row = connection.execute(
        """SELECT * FROM career_os_application_plan_supersessions
           WHERE replacement_plan_id=?""",
        (envelope.plan_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Committed replacement plan lacks supersession ledger")
    row = dict(row)
    expected = {
        "prior_plan_id": supersession.prior_plan_id,
        "tenant_id": envelope.tenant_id,
        "user_id": envelope.user_id,
        "application_id": envelope.application_id,
        "session_id": supersession.session_id,
        "prior_plan_digest": supersession.prior_plan_digest,
        "replacement_plan_digest": supersession.replacement_plan_digest,
        "resolution_digest": supersession.resolution_digest,
        "browser_form_digest": supersession.browser_form_digest,
        "checkpoint_id": supersession.checkpoint_id,
    }
    if any(str(row[key]) != str(value) for key, value in expected.items()):
        raise ValueError("Committed plan supersession ledger conflicts with replay")
    session = connection.execute(
        """SELECT plan_id FROM complete_application_sessions
           WHERE session_id=? AND application_id=?""",
        (supersession.session_id, envelope.application_id),
    ).fetchone()
    job = connection.execute(
        """SELECT job_id,plan_id FROM complete_application_prepare_jobs
           WHERE job_id=? AND session_id=?""",
        (row["prepare_job_id"], supersession.session_id),
    ).fetchone()
    if (
        session is None
        or job is None
        or str(session["plan_id"]) != envelope.plan_id
        or str(job["plan_id"]) != envelope.plan_id
    ):
        raise ValueError("Committed plan supersession execution binding is invalid")
    return supersession.session_id, str(row["prepare_job_id"])

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
        if envelope.supersession is not None and not runtime_supersession_enabled():
            return PlanHandoffResult(
                False,
                False,
                "REJECTED",
                error="plan supersession disabled",
            )

        body_sha256 = hashlib.sha256(body).hexdigest()
        plan = dict(envelope.plan)
        resume = dict(plan["resume"])
        job = dict(plan["job"])
        accepted_at = datetime.now(UTC).isoformat()
        # Hunter's plan idempotency key is immutable plan metadata. The handoff
        # id remains the replay identity in signed transport headers.
        idempotency_key = str(plan.get("idempotency_key") or envelope.plan_digest)

        resumed_session_id: str | None = None
        preparation_job_id: str | None = None
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
                    replay_binding = _supersession_replay_locked(connection, envelope)
                    if replay_binding is not None:
                        resumed_session_id, preparation_job_id = replay_binding
                    return PlanHandoffResult(
                        True,
                        True,
                        "PLAN_ACCEPTED",
                        handoff_id=envelope.handoff_id,
                        plan_id=envelope.plan_id,
                        plan_digest=envelope.plan_digest,
                        resumed_session_id=resumed_session_id,
                        preparation_job_id=preparation_job_id,
                    )

                replay = connection.execute(
                    "SELECT body_sha256,plan_id FROM career_os_application_plans "
                    "WHERE handoff_id=?",
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
                    replay_binding = _supersession_replay_locked(connection, envelope)
                    if replay_binding is not None:
                        resumed_session_id, preparation_job_id = replay_binding
                    return PlanHandoffResult(
                        True,
                        True,
                        "PLAN_ACCEPTED",
                        handoff_id=envelope.handoff_id,
                        plan_id=str(replay["plan_id"]),
                        plan_digest=envelope.plan_digest,
                        resumed_session_id=resumed_session_id,
                        preparation_job_id=preparation_job_id,
                    )

                supersession_target = _supersession_target_locked(connection, envelope)
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
                if supersession_target is not None:
                    resumed_session_id, preparation_job_id = _commit_supersession_locked(
                        connection,
                        envelope=envelope,
                        session=supersession_target[0],
                        prepare_job=supersession_target[1],
                        accepted_at=accepted_at,
                    )
        except sqlite3.IntegrityError:
            return PlanHandoffResult(
                False, False, "REJECTED", error="plan identity conflict"
            )
        except (LookupError, PermissionError, ValueError) as error:
            return PlanHandoffResult(False, False, "REJECTED", error=str(error))

        return PlanHandoffResult(
            True,
            False,
            "PLAN_ACCEPTED",
            handoff_id=envelope.handoff_id,
            plan_id=envelope.plan_id,
            plan_digest=envelope.plan_digest,
            resumed_session_id=resumed_session_id,
            preparation_job_id=preparation_job_id,
        )
