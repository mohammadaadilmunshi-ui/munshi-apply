"""Checkpointed Complete Application Loop orchestration for MUNSHI Apply.

This module is intentionally an orchestration layer over the existing Apply
application/checkpoint/resolution architecture. Browser mechanics remain behind
`BrowserExecutionAdapter`; this file does not implement a new browser engine.
High-risk external actions are default-off and final submit requires an explicit
review-bound command plus independent success evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from .checkpoint_store import ApplicationCheckpointStore
from .database import Database, canonical_json
from .models import ResolutionTaskPayload, ResolutionTaskResolutionPayload
from .resolution_task_store import ResolutionTaskStore

BACKGROUND_PREPARE_ENV = "MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED"
FINAL_REVIEW_ENV = "MUNSHI_FINAL_REVIEW_ENABLED"
FINAL_SUBMIT_ENV = "MUNSHI_FINAL_SUBMIT_ENABLED"

SESSION_STATES = frozenset(
    {
        "PLAN_ACCEPTED",
        "SESSION_STARTING",
        "JOB_VERIFIED",
        "FORM_DISCOVERED",
        "PREPARING",
        "NEEDS_INPUT",
        "READY_FOR_REVIEW",
        "READY_TO_SUBMIT",
        "SUBMITTING",
        "SUBMITTED",
        "VERIFIED",
        "SUBMISSION_UNVERIFIED",
        "BLOCKED",
        "FAILED_SAFELY",
    }
)

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PLAN_ACCEPTED": {"SESSION_STARTING", "BLOCKED", "FAILED_SAFELY"},
    "SESSION_STARTING": {"JOB_VERIFIED", "BLOCKED", "FAILED_SAFELY"},
    "JOB_VERIFIED": {"FORM_DISCOVERED", "BLOCKED", "FAILED_SAFELY"},
    "FORM_DISCOVERED": {"PREPARING", "BLOCKED", "FAILED_SAFELY"},
    "PREPARING": {"NEEDS_INPUT", "READY_FOR_REVIEW", "BLOCKED", "FAILED_SAFELY"},
    "NEEDS_INPUT": {"PREPARING", "BLOCKED", "FAILED_SAFELY"},
    "READY_FOR_REVIEW": {"READY_TO_SUBMIT", "PREPARING", "BLOCKED", "FAILED_SAFELY"},
    "READY_TO_SUBMIT": {"SUBMITTING", "PREPARING", "BLOCKED", "FAILED_SAFELY"},
    "SUBMITTING": {"SUBMITTED", "VERIFIED", "SUBMISSION_UNVERIFIED", "BLOCKED", "FAILED_SAFELY"},
    "SUBMITTED": {"VERIFIED", "SUBMISSION_UNVERIFIED"},
    "VERIFIED": {"VERIFIED"},
    "SUBMISSION_UNVERIFIED": {"SUBMISSION_UNVERIFIED"},
    "BLOCKED": {"BLOCKED"},
    "FAILED_SAFELY": {"FAILED_SAFELY"},
}


class BrowserExecutionAdapter(Protocol):
    """Port implemented by existing provider/browser runtime or local fixtures."""

    def inspect_job(self, *, plan: dict[str, Any]) -> dict[str, Any]: ...

    def prepare_form(
        self,
        *,
        plan: dict[str, Any],
        checkpoint: dict[str, Any] | None,
        resolved_values: dict[str, Any],
    ) -> dict[str, Any]: ...

    def submit(self, *, plan: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SessionResult:
    session_id: str
    application_id: str
    plan_id: str
    state: str
    state_version: int


def _truthy(name: str) -> bool:
    return str(os.getenv(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _event_id(replay_identity: str) -> str:
    return "loop-event-" + hashlib.sha256(replay_identity.encode("utf-8")).hexdigest()[:32]


def _safe_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """Reject common secret-bearing keys from durable event evidence."""
    forbidden = {
        "password",
        "passcode",
        "otp",
        "token",
        "oauth_token",
        "api_key",
        "authorization_header",
        "hmac_secret",
    }
    result: dict[str, Any] = {}
    for key, item in value.items():
        if str(key).casefold() in forbidden:
            raise ValueError(f"Execution evidence may not persist secret field {key}")
        result[str(key)] = item
    return result


class CompleteApplicationLoopService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.checkpoints = ApplicationCheckpointStore(database)
        self.resolutions = ResolutionTaskStore(database)

    def _plan(self, plan_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM career_os_application_plans WHERE plan_id=?",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Accepted Application Plan was not found")
        result = dict(row)
        result["plan"] = json.loads(result.pop("plan_json"))
        return result

    def _session(self, session_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM complete_application_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Execution session was not found")
        return dict(row)

    def _ensure_local_application(self, plan_record: dict[str, Any]) -> None:
        plan = dict(plan_record["plan"])
        job = dict(plan["job"])
        resume = dict(plan["resume"])
        now = _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job_id = str(job["id"])
            existing_job = connection.execute(
                "SELECT job_id FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if existing_job is None:
                connection.execute(
                    """INSERT INTO jobs(
                           job_id,company,role,job_url,application_url,location,
                           description,created_at,updated_at
                       ) VALUES (?,?,?,?,?,?,NULL,?,?)""",
                    (
                        job_id,
                        job.get("company"),
                        job.get("title"),
                        job.get("job_url"),
                        job.get("apply_url"),
                        job.get("location"),
                        now,
                        now,
                    ),
                )

            resume_sha = str(resume["artifact_sha256"])
            resume_row = connection.execute(
                "SELECT resume_id FROM resumes WHERE sha256=?", (resume_sha,)
            ).fetchone()
            if resume_row is None:
                resume_id = f"hunter-artifact:{resume['artifact_id']}"
                connection.execute(
                    """INSERT INTO resumes(
                           resume_id,family,version,sha256,filename,source_path,
                           role_family,active,created_at
                       ) VALUES (?,'hunter-application-plan',?,?,?,?,NULL,1,?)""",
                    (
                        resume_id,
                        int(resume.get("version_number") or 1),
                        resume_sha,
                        str(resume["filename"]),
                        str(resume["artifact_reference"]),
                        now,
                    ),
                )
            else:
                resume_id = str(resume_row["resume_id"])

            application_id = str(plan_record["application_id"])
            existing = connection.execute(
                "SELECT * FROM applications WHERE application_id=?",
                (application_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO applications(
                           application_id,job_id,status,resume_id,job_signal_score,
                           submitted_at,created_at,updated_at
                       ) VALUES (?,?,'PLAN_ACCEPTED',?,NULL,NULL,?,?)""",
                    (application_id, job_id, resume_id, now, now),
                )
            else:
                if str(existing["job_id"] or "") not in {"", job_id}:
                    raise ValueError("Existing Apply application is bound to another job")
                existing_resume = existing["resume_id"]
                if existing_resume:
                    stored = connection.execute(
                        "SELECT sha256 FROM resumes WHERE resume_id=?", (existing_resume,)
                    ).fetchone()
                    if stored is not None and str(stored["sha256"]) != resume_sha:
                        raise ValueError("Existing Apply application is bound to another resume")
                if str(existing["status"]) in {
                    "SUBMITTED",
                    "VERIFIED",
                    "SUBMISSION_UNVERIFIED",
                    "COMPLETE",
                }:
                    raise ValueError("Application already reached a submission outcome")
                connection.execute(
                    "UPDATE applications SET job_id=?,resume_id=?,updated_at=? WHERE application_id=?",
                    (job_id, resume_id, now, application_id),
                )

    def _transition(
        self,
        session: dict[str, Any],
        state: str,
        *,
        current_url: str | None = None,
        observed_job_identity: str | None = None,
        browser_form_digest: str | None = None,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        current = str(session["state"])
        if state not in SESSION_STATES or state not in _ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"Session state cannot move from {current} to {state}")
        now = _now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """UPDATE complete_application_sessions
                   SET state=?,state_version=state_version+1,current_url=COALESCE(?,current_url),
                       observed_job_identity=COALESCE(?,observed_job_identity),
                       browser_form_digest=COALESCE(?,browser_form_digest),
                       checkpoint_id=COALESCE(?,checkpoint_id),updated_at=?
                   WHERE session_id=? AND state_version=?""",
                (
                    state,
                    current_url,
                    observed_job_identity,
                    browser_form_digest,
                    checkpoint_id,
                    now,
                    session["session_id"],
                    int(session["state_version"]),
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Execution session changed concurrently")
            connection.execute(
                "UPDATE applications SET status=?,updated_at=? WHERE application_id=?",
                (state, now, session["application_id"]),
            )
        return self._session(str(session["session_id"]))

    def _record_event(
        self,
        *,
        session: dict[str, Any],
        event_type: str,
        replay_identity: str,
        evidence: dict[str, Any],
        checkpoint: dict[str, Any] | None = None,
    ) -> bool:
        safe = _safe_evidence(evidence)
        event_id = _event_id(replay_identity)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM complete_application_execution_events WHERE replay_identity=?",
                (replay_identity,),
            ).fetchone()
            if prior is not None:
                if (
                    str(prior["event_type"]) != event_type
                    or str(prior["evidence_json"]) != canonical_json(safe)
                    or str(prior["checkpoint_json"] or "")
                    != (canonical_json(checkpoint) if checkpoint is not None else "")
                ):
                    raise ValueError("Execution replay identity was reused with different evidence")
                return False
            connection.execute(
                """INSERT INTO complete_application_execution_events(
                       event_id,application_id,plan_id,session_id,provider,event_type,
                       replay_identity,evidence_json,checkpoint_json,occurred_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    session["application_id"],
                    session["plan_id"],
                    session["session_id"],
                    session["provider"],
                    event_type,
                    replay_identity,
                    canonical_json(safe),
                    canonical_json(checkpoint) if checkpoint is not None else None,
                    _now(),
                ),
            )
        return True

    def _next_checkpoint(
        self,
        *,
        session: dict[str, Any],
        state: str,
        page_id: str,
        page_fingerprint: str,
        completed: list[str],
        pending: list[str],
        resume_id: str,
        resume_sha256: str,
    ) -> dict[str, Any]:
        latest = self.checkpoints.latest(str(session["application_id"]))
        sequence = 0 if latest is None else int(latest["sequence"]) + 1
        checkpoint = {
            "checkpoint_id": f"checkpoint-{uuid4()}",
            "application_id": str(session["application_id"]),
            "sequence": sequence,
            "state": state,
            "page_id": page_id,
            "page_fingerprint": page_fingerprint,
            "completed_control_ids": sorted(set(completed)),
            "pending_control_ids": sorted(set(pending)),
            "selected_resume_id": resume_id,
            "selected_resume_sha256": resume_sha256,
            "created_at": _now(),
        }
        self.checkpoints.save(checkpoint)
        return checkpoint

    def start_session(self, *, plan_id: str) -> SessionResult:
        if not _truthy(BACKGROUND_PREPARE_ENV):
            raise RuntimeError("Apply background preparation is disabled")
        plan_record = self._plan(plan_id)
        plan = dict(plan_record["plan"])
        if plan.get("expected_state") != "READY_TO_APPLY" or plan.get("executable") is not True:
            raise ValueError("Accepted Application Plan is not execution-ready")
        if plan.get("submission_authority") is not False:
            raise ValueError("Accepted Application Plan unexpectedly carries submission authority")
        self._ensure_local_application(plan_record)

        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM complete_application_sessions WHERE application_id=? AND plan_id=?",
                (plan_record["application_id"], plan_id),
            ).fetchone()
            if existing is None:
                session_id = f"apply-session-{uuid4()}"
                now = _now()
                connection.execute(
                    """INSERT INTO complete_application_sessions(
                           session_id,application_id,plan_id,provider,state,state_version,
                           created_at,updated_at
                       ) VALUES (?,?,?,?,'PLAN_ACCEPTED',1,?,?)""",
                    (
                        session_id,
                        plan_record["application_id"],
                        plan_id,
                        str(plan_record["provider"]),
                        now,
                        now,
                    ),
                )
            else:
                session_id = str(existing["session_id"])
        session = self._session(session_id)
        if session["state"] == "PLAN_ACCEPTED":
            session = self._transition(session, "SESSION_STARTING")
            self._record_event(
                session=session,
                event_type="SESSION_STARTED",
                replay_identity=f"{session_id}:session-started",
                evidence={"plan_id": plan_id, "provider": session["provider"]},
            )
        return SessionResult(
            session_id=session_id,
            application_id=str(session["application_id"]),
            plan_id=plan_id,
            state=str(session["state"]),
            state_version=int(session["state_version"]),
        )

    def _resolution_task(
        self,
        *,
        session: dict[str, Any],
        checkpoint: dict[str, Any],
        unresolved: dict[str, Any],
    ) -> ResolutionTaskPayload:
        question_key = str(
            unresolved.get("question_key")
            or unresolved.get("control_id")
            or unresolved.get("question")
            or "unknown"
        ).strip()
        task_id = "plan-resolution-" + hashlib.sha256(
            f"{session['plan_id']}\0{session['session_id']}\0{question_key}".encode("utf-8")
        ).hexdigest()[:32]
        existing = self.resolutions.get(task_id)
        if existing is not None:
            return existing
        semantic = str(unresolved.get("semantic_type") or "unknown")
        sensitivity = str(unresolved.get("sensitivity") or "NORMAL").upper()
        category = "CAPTCHA" if semantic.casefold() == "captcha" else "MISSING_FACT"
        risk = "HIGH" if sensitivity in {"PROTECTED", "SELF_ID", "CREDENTIAL", "POST_OFFER"} else "MEDIUM"
        grouping = "NONE" if category == "CAPTCHA" else "EXACT_QUESTION"
        now = datetime.now(UTC)
        task = ResolutionTaskPayload.model_validate(
            {
                "schemaVersion": 1,
                "taskId": task_id,
                "applicationId": session["application_id"],
                "sessionId": session["session_id"],
                "checkpointId": checkpoint["checkpoint_id"],
                "pageId": checkpoint["page_id"],
                "controlId": unresolved.get("control_id"),
                "questionId": unresolved.get("question_id"),
                "question": unresolved.get("question") or question_key,
                "semanticType": semantic,
                "category": category,
                "status": "WAITING_FOR_USER",
                "riskLevel": risk,
                "autoResolvable": False,
                "requiresUser": True,
                "groupingScope": grouping,
                "groupKey": None if grouping == "NONE" else question_key,
                "sourceRefs": [f"application-plan:{session['plan_id']}"],
                "evidenceRefs": [],
                "attemptedResolvers": ["CURRENT_SESSION", "APPROVED_ANSWER_MEMORY"],
                "reason": str(unresolved.get("reason") or "Required field has no safe execution value"),
                "resolution": None,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        self.resolutions.upsert(task)
        return task

    def _resolved_values(self, application_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for task in self.resolutions.list(application_id=application_id, status="RESOLVED"):
            if task.resolution is None:
                continue
            key = task.group_key or task.control_id or task.task_id
            result[str(key)] = task.resolution.value
        return result

    def resolve_task(
        self,
        *,
        task_id: str,
        value: Any,
        approved_by_user: bool = True,
    ) -> dict[str, Any]:
        """Resolve a local execution task; never promote it to Hunter canonical truth."""
        task = self.resolutions.get(task_id)
        if task is None:
            raise LookupError("Resolution task was not found")
        if task.status == "RESOLVED":
            assert task.resolution is not None
            if task.resolution.value != value:
                raise ValueError("Resolved task cannot be changed")
            return task.wire_payload()
        if task.risk_level == "HIGH":
            if not isinstance(value, str) or not value.startswith("hunter-secure://"):
                raise ValueError("High-risk resolution requires a Hunter secure resolver reference")
        now = datetime.now(UTC)
        resolved = task.model_copy(
            update={
                "status": "RESOLVED",
                "resolution": ResolutionTaskResolutionPayload(
                    value=value,
                    source="USER",
                    evidenceRefs=[],
                    approvedByUser=bool(approved_by_user),
                    resolvedAt=now,
                ),
                "updated_at": now,
            }
        )
        self.resolutions.upsert(resolved)
        session = self._session(str(task.session_id)) if task.session_id else None
        if session is not None:
            self._record_event(
                session=session,
                event_type="RESOLUTION_SUPPLIED",
                replay_identity=f"{task.task_id}:resolved:{_sha(value)}",
                evidence={
                    "task_id": task.task_id,
                    "question_key": task.group_key,
                    "risk_level": task.risk_level,
                    "value_persisted_as": "secure_reference" if task.risk_level == "HIGH" else "local_execution_value",
                    "canonical_truth_promoted": False,
                },
            )
        return resolved.wire_payload()

    def prepare_session(
        self,
        *,
        session_id: str,
        adapter: BrowserExecutionAdapter,
    ) -> SessionResult:
        if not _truthy(BACKGROUND_PREPARE_ENV):
            raise RuntimeError("Apply background preparation is disabled")
        session = self._session(session_id)
        if str(session["state"]) not in {
            "SESSION_STARTING",
            "JOB_VERIFIED",
            "FORM_DISCOVERED",
            "PREPARING",
            "NEEDS_INPUT",
            "READY_FOR_REVIEW",
            "READY_TO_SUBMIT",
        }:
            raise ValueError("Execution session cannot be prepared from its current state")
        plan_record = self._plan(str(session["plan_id"]))
        plan = dict(plan_record["plan"])

        observation = adapter.inspect_job(plan=plan)
        provider = str(observation.get("provider") or "").upper()
        expected_provider = str(plan_record["provider"]).upper()
        expected_job = str(plan["job"]["id"])
        observed_job = str(observation.get("job_id") or "")
        if provider != expected_provider or observed_job != expected_job:
            if session["state"] != "BLOCKED":
                session = self._transition(
                    session,
                    "BLOCKED",
                    current_url=str(observation.get("current_url") or ""),
                    observed_job_identity=observed_job,
                )
            self._record_event(
                session=session,
                event_type="BLOCKED",
                replay_identity=f"{session_id}:wrong-job:{provider}:{observed_job}",
                evidence={
                    "reason": "wrong_job_or_provider",
                    "expected_provider": expected_provider,
                    "observed_provider": provider,
                    "expected_job_id": expected_job,
                    "observed_job_id": observed_job,
                },
            )
            return SessionResult(session_id, session["application_id"], session["plan_id"], "BLOCKED", int(session["state_version"]))

        if session["state"] == "SESSION_STARTING":
            session = self._transition(
                session,
                "JOB_VERIFIED",
                current_url=str(observation.get("current_url") or ""),
                observed_job_identity=observed_job,
            )
            self._record_event(
                session=session,
                event_type="JOB_VERIFIED",
                replay_identity=f"{session_id}:job-verified:{provider}:{observed_job}",
                evidence={"provider": provider, "job_id": observed_job},
            )
        if session["state"] == "JOB_VERIFIED":
            session = self._transition(session, "FORM_DISCOVERED")
            self._record_event(
                session=session,
                event_type="FORM_DISCOVERED",
                replay_identity=f"{session_id}:form-discovered:{observation.get('page_fingerprint')}",
                evidence={"page_fingerprint": observation.get("page_fingerprint")},
            )
        if session["state"] in {"FORM_DISCOVERED", "NEEDS_INPUT", "READY_FOR_REVIEW", "READY_TO_SUBMIT"}:
            session = self._transition(session, "PREPARING")

        latest = self.checkpoints.latest(str(session["application_id"]))
        prepared = adapter.prepare_form(
            plan=plan,
            checkpoint=latest,
            resolved_values=self._resolved_values(str(session["application_id"])),
        )
        if str(prepared.get("provider") or "").upper() != expected_provider:
            session = self._transition(session, "BLOCKED")
            self._record_event(
                session=session,
                event_type="BLOCKED",
                replay_identity=f"{session_id}:provider-changed:{prepared.get('provider')}",
                evidence={"reason": "provider_changed_during_prepare"},
            )
            return SessionResult(session_id, session["application_id"], session["plan_id"], "BLOCKED", int(session["state_version"]))
        if str(prepared.get("job_id") or "") != expected_job:
            session = self._transition(session, "BLOCKED")
            self._record_event(
                session=session,
                event_type="BLOCKED",
                replay_identity=f"{session_id}:job-changed:{prepared.get('job_id')}",
                evidence={"reason": "job_changed_during_prepare"},
            )
            return SessionResult(session_id, session["application_id"], session["plan_id"], "BLOCKED", int(session["state_version"]))

        resume = dict(plan["resume"])
        if prepared.get("resume_uploaded") is not True or str(prepared.get("resume_sha256") or "") != str(resume["artifact_sha256"]):
            session = self._transition(session, "FAILED_SAFELY")
            self._record_event(
                session=session,
                event_type="FAILED_SAFELY",
                replay_identity=f"{session_id}:resume-verification-failed:{prepared.get('resume_sha256')}",
                evidence={"reason": "resume_upload_not_verified"},
            )
            return SessionResult(session_id, session["application_id"], session["plan_id"], "FAILED_SAFELY", int(session["state_version"]))

        completed = [str(value) for value in prepared.get("completed_control_ids") or []]
        pending = [str(value) for value in prepared.get("pending_control_ids") or []]
        checkpoint = self._next_checkpoint(
            session=session,
            state="QUESTIONS",
            page_id=str(prepared.get("page_id") or observation.get("page_id") or "application-form"),
            page_fingerprint=str(prepared.get("page_fingerprint") or observation.get("page_fingerprint") or "unknown"),
            completed=completed,
            pending=pending,
            resume_id=str(resume["artifact_id"]),
            resume_sha256=str(resume["artifact_sha256"]),
        )
        form_digest = str(prepared.get("form_digest") or "")
        if len(form_digest) != 64:
            session = self._transition(session, "FAILED_SAFELY", checkpoint_id=checkpoint["checkpoint_id"])
            self._record_event(
                session=session,
                event_type="FAILED_SAFELY",
                replay_identity=f"{session_id}:invalid-form-digest:{checkpoint['sequence']}",
                evidence={"reason": "browser_form_digest_missing_or_invalid"},
                checkpoint=checkpoint,
            )
            return SessionResult(session_id, session["application_id"], session["plan_id"], "FAILED_SAFELY", int(session["state_version"]))

        unresolved = list(prepared.get("unresolved") or [])
        validation_errors = [str(value) for value in prepared.get("validation_errors") or []]
        review_fields = list(prepared.get("review_fields") or [])
        event_evidence = {
            "required_fields": int(prepared.get("required_fields") or 0),
            "completed_required_fields": int(prepared.get("completed_required_fields") or 0),
            "unresolved_count": len(unresolved),
            "validation_errors": validation_errors,
            "resume_uploaded": True,
            "resume_sha256": resume["artifact_sha256"],
            "form_digest": form_digest,
            "review_fields": review_fields,
        }
        self._record_event(
            session=session,
            event_type="FORM_PREPARED",
            replay_identity=f"{session_id}:form-prepared:{form_digest}:{checkpoint['sequence']}",
            evidence=event_evidence,
            checkpoint=checkpoint,
        )

        # Any new material form state invalidates a prior approval.
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE final_application_reviews
                   SET invalidated_at=COALESCE(invalidated_at,?),
                       invalidation_reason=COALESCE(invalidation_reason,'browser_form_changed')
                   WHERE application_id=? AND plan_id=? AND approved_at IS NOT NULL
                     AND invalidated_at IS NULL AND browser_form_digest<>?""",
                (_now(), session["application_id"], session["plan_id"], form_digest),
            )

        if unresolved:
            for item in unresolved:
                self._resolution_task(session=session, checkpoint=checkpoint, unresolved=dict(item))
            session = self._transition(
                session,
                "NEEDS_INPUT",
                current_url=str(prepared.get("current_url") or observation.get("current_url") or ""),
                browser_form_digest=form_digest,
                checkpoint_id=checkpoint["checkpoint_id"],
            )
            self._record_event(
                session=session,
                event_type="NEEDS_INPUT",
                replay_identity=f"{session_id}:needs-input:{form_digest}:{len(unresolved)}",
                evidence={"unresolved_count": len(unresolved)},
                checkpoint=checkpoint,
            )
        elif validation_errors or int(prepared.get("completed_required_fields") or 0) < int(prepared.get("required_fields") or 0):
            session = self._transition(
                session,
                "FAILED_SAFELY",
                browser_form_digest=form_digest,
                checkpoint_id=checkpoint["checkpoint_id"],
            )
            self._record_event(
                session=session,
                event_type="FAILED_SAFELY",
                replay_identity=f"{session_id}:validation-errors:{form_digest}",
                evidence={"validation_errors": validation_errors, "reason": "required_form_not_complete"},
                checkpoint=checkpoint,
            )
        else:
            session = self._transition(
                session,
                "READY_FOR_REVIEW",
                current_url=str(prepared.get("current_url") or observation.get("current_url") or ""),
                browser_form_digest=form_digest,
                checkpoint_id=checkpoint["checkpoint_id"],
            )
            self._record_event(
                session=session,
                event_type="READY_FOR_REVIEW",
                replay_identity=f"{session_id}:ready-review:{form_digest}",
                evidence={"form_digest": form_digest, "resume_sha256": resume["artifact_sha256"]},
                checkpoint=checkpoint,
            )
        return SessionResult(
            session_id,
            str(session["application_id"]),
            str(session["plan_id"]),
            str(session["state"]),
            int(session["state_version"]),
        )

    def _latest_prepared_evidence(self, session_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT evidence_json FROM complete_application_execution_events
                   WHERE session_id=? AND event_type='FORM_PREPARED'
                   ORDER BY occurred_at DESC,event_id DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        if row is None:
            raise LookupError("No prepared browser form evidence exists for review")
        return json.loads(str(row["evidence_json"]))

    def build_review(self, *, session_id: str) -> dict[str, Any]:
        if not _truthy(FINAL_REVIEW_ENV):
            raise RuntimeError("Final application review is disabled")
        session = self._session(session_id)
        if str(session["state"]) != "READY_FOR_REVIEW":
            raise ValueError("Session is not ready for final review")
        plan_record = self._plan(str(session["plan_id"]))
        plan = dict(plan_record["plan"])
        prepared = self._latest_prepared_evidence(session_id)
        form_digest = str(session["browser_form_digest"] or "")
        resume = dict(plan["resume"])

        open_tasks = [
            task
            for task in self.resolutions.list(application_id=str(session["application_id"]))
            if task.status not in {"RESOLVED", "FAILED", "EXPIRED"}
        ]
        if open_tasks:
            raise ValueError("Unresolved application inputs still exist")

        answers: list[dict[str, Any]] = []
        for answer in plan.get("answers") or []:
            item = dict(answer)
            sensitivity = str(item.get("sensitivity_class") or "NORMAL")
            answers.append(
                {
                    "question_key": item.get("question_key"),
                    "question_family": item.get("question_family"),
                    "display_value": (
                        item.get("display_value")
                        if sensitivity == "NORMAL"
                        else "[protected or sensitive value]"
                    ),
                    "sensitivity_class": sensitivity,
                    "requires_review": bool(item.get("requires_review")),
                    "source": item.get("source"),
                }
            )
        review_snapshot = {
            "application_id": session["application_id"],
            "plan_id": session["plan_id"],
            "session_id": session_id,
            "job": plan["job"],
            "provider": plan_record["provider"],
            "destination_url": session["current_url"],
            "resume": {
                "filename": resume["filename"],
                "version_id": resume["version_id"],
                "artifact_id": resume["artifact_id"],
                "sha256": resume["artifact_sha256"],
                "truth_status": "BOUND",
                "job_binding": resume.get("source_bindings", {}).get("job"),
            },
            "application": {
                "required_fields": prepared.get("required_fields"),
                "completed": prepared.get("completed_required_fields"),
                "unresolved": prepared.get("unresolved_count"),
                "warnings": prepared.get("validation_errors") or [],
            },
            "answers": answers,
            "browser_verification": {
                "form_digest": form_digest,
                "resume_uploaded": prepared.get("resume_uploaded") is True,
                "resume_sha256": prepared.get("resume_sha256"),
                "validation_errors": prepared.get("validation_errors") or [],
                "review_fields": prepared.get("review_fields") or [],
            },
            "submission_readiness": "READY_FOR_REVIEW",
        }
        review_digest = _sha(review_snapshot)
        review_id = "review-" + review_digest[:32]
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM final_application_reviews WHERE review_id=?",
                (review_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO final_application_reviews(
                           review_id,application_id,plan_id,session_id,review_digest,
                           plan_digest,browser_form_digest,resume_digest,review_json,
                           approved_at,invalidated_at,invalidation_reason,created_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?)""",
                    (
                        review_id,
                        session["application_id"],
                        session["plan_id"],
                        session_id,
                        review_digest,
                        plan_record["plan_digest"],
                        form_digest,
                        resume["artifact_sha256"],
                        canonical_json(review_snapshot),
                        _now(),
                    ),
                )
        return {
            "review_id": review_id,
            "review_digest": review_digest,
            "review": review_snapshot,
            "approved": False,
        }

    def approve_review(self, *, review_id: str) -> dict[str, Any]:
        if not _truthy(FINAL_REVIEW_ENV):
            raise RuntimeError("Final application review is disabled")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM final_application_reviews WHERE review_id=?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Final review was not found")
        review = dict(row)
        if review["invalidated_at"] is not None:
            raise ValueError("Final review approval was invalidated")
        session = self._session(str(review["session_id"]))
        plan_record = self._plan(str(review["plan_id"]))
        plan = dict(plan_record["plan"])
        if str(session["state"]) != "READY_FOR_REVIEW":
            raise ValueError("Browser session is no longer ready for this review")
        if str(session["browser_form_digest"]) != str(review["browser_form_digest"]):
            raise ValueError("Browser form changed after review was created")
        if str(plan_record["plan_digest"]) != str(review["plan_digest"]):
            raise ValueError("Application Plan changed after review was created")
        if str(plan["resume"]["artifact_sha256"]) != str(review["resume_digest"]):
            raise ValueError("Resume changed after review was created")
        open_tasks = [
            task
            for task in self.resolutions.list(application_id=str(session["application_id"]))
            if task.status not in {"RESOLVED", "FAILED", "EXPIRED"}
        ]
        if open_tasks:
            raise ValueError("Unresolved application inputs still exist")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT approved_at,invalidated_at FROM final_application_reviews WHERE review_id=?",
                (review_id,),
            ).fetchone()
            if current["invalidated_at"] is not None:
                raise ValueError("Final review approval was invalidated")
            if current["approved_at"] is None:
                connection.execute(
                    "UPDATE final_application_reviews SET approved_at=? WHERE review_id=?",
                    (_now(), review_id),
                )
        session = self._transition(session, "READY_TO_SUBMIT")
        self._record_event(
            session=session,
            event_type="REVIEW_APPROVED",
            replay_identity=f"{review_id}:approved",
            evidence={
                "review_id": review_id,
                "review_digest": review["review_digest"],
                "plan_digest": review["plan_digest"],
                "browser_form_digest": review["browser_form_digest"],
                "resume_digest": review["resume_digest"],
            },
        )
        return {
            "review_id": review_id,
            "approved": True,
            "state": "READY_TO_SUBMIT",
            "review_digest": str(review["review_digest"]),
        }

    def _event_chain_digest(self, session_id: str) -> str:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT event_id,event_type,replay_identity,evidence_json,checkpoint_json,occurred_at
                   FROM complete_application_execution_events
                   WHERE session_id=? ORDER BY occurred_at,event_id""",
                (session_id,),
            ).fetchall()
        return _sha([dict(row) for row in rows])

    def _receipt_for_command(self, command_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM application_submission_receipts WHERE command_id=?",
                (command_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["receipt"] = json.loads(result.pop("receipt_json"))
        result["success_evidence"] = json.loads(result.pop("success_evidence_json"))
        return result

    @staticmethod
    def _verified_success_evidence(result: dict[str, Any]) -> bool:
        evidence = result.get("success_evidence")
        if not isinstance(evidence, dict):
            return False
        recognized = {
            "success_page",
            "confirmation_message",
            "provider_application_id",
            "url_transition",
            "completion_marker",
        }
        return any(key in evidence and evidence[key] not in (None, "", False) for key in recognized)

    def submit(
        self,
        *,
        review_id: str,
        idempotency_key: str,
        adapter: BrowserExecutionAdapter,
    ) -> dict[str, Any]:
        if not _truthy(FINAL_SUBMIT_ENV):
            raise RuntimeError("Final submit authority is disabled")
        key = str(idempotency_key or "").strip()
        if not key:
            raise ValueError("Explicit Submit command idempotency key is required")
        with self.database.connect() as connection:
            review_row = connection.execute(
                "SELECT * FROM final_application_reviews WHERE review_id=?",
                (review_id,),
            ).fetchone()
        if review_row is None:
            raise LookupError("Approved review was not found")
        review = dict(review_row)
        if review["approved_at"] is None or review["invalidated_at"] is not None:
            raise ValueError("Explicit Submit requires a current approved review")
        session = self._session(str(review["session_id"]))
        if str(session["state"]) != "READY_TO_SUBMIT":
            existing = None
            with self.database.connect() as connection:
                existing = connection.execute(
                    "SELECT * FROM final_submit_commands WHERE idempotency_key=?",
                    (key,),
                ).fetchone()
            if existing is not None:
                receipt = self._receipt_for_command(str(existing["command_id"]))
                return receipt or {"command": dict(existing), "replayed": True}
            raise ValueError("Browser session is not READY_TO_SUBMIT")
        if str(session["browser_form_digest"]) != str(review["browser_form_digest"]):
            raise ValueError("Browser form changed after final review approval")

        plan_record = self._plan(str(review["plan_id"]))
        plan = dict(plan_record["plan"])
        if str(plan_record["plan_digest"]) != str(review["plan_digest"]):
            raise ValueError("Application Plan changed after final review approval")
        if str(plan["resume"]["artifact_sha256"]) != str(review["resume_digest"]):
            raise ValueError("Resume changed after final review approval")

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM final_submit_commands WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            if existing is not None:
                if str(existing["review_id"]) != review_id:
                    raise ValueError("Submit idempotency key belongs to another review")
                receipt = self._receipt_for_command(str(existing["command_id"]))
                return receipt or {"command": dict(existing), "replayed": True}
            prior_review = connection.execute(
                "SELECT command_id FROM final_submit_commands WHERE application_id=? AND plan_id=? AND review_id=?",
                (review["application_id"], review["plan_id"], review_id),
            ).fetchone()
            if prior_review is not None:
                receipt = self._receipt_for_command(str(prior_review["command_id"]))
                return receipt or {"command_id": prior_review["command_id"], "replayed": True}
            command_id = f"submit-command-{uuid4()}"
            command_payload = {
                "application_id": review["application_id"],
                "plan_id": review["plan_id"],
                "session_id": review["session_id"],
                "review_id": review_id,
                "review_digest": review["review_digest"],
                "plan_digest": review["plan_digest"],
                "browser_form_digest": review["browser_form_digest"],
                "resume_digest": review["resume_digest"],
            }
            connection.execute(
                """INSERT INTO final_submit_commands(
                       command_id,application_id,plan_id,session_id,review_id,idempotency_key,
                       command_digest,state,issued_at
                   ) VALUES (?,?,?,?,?,?,?,'SUBMITTING',?)""",
                (
                    command_id,
                    review["application_id"],
                    review["plan_id"],
                    review["session_id"],
                    review_id,
                    key,
                    _sha(command_payload),
                    _now(),
                ),
            )
        session = self._transition(session, "SUBMITTING")
        self._record_event(
            session=session,
            event_type="SUBMITTING",
            replay_identity=f"{command_id}:submit-start",
            evidence={"command_id": command_id, "review_id": review_id},
        )

        # This is the only adapter call that may perform the final employer action.
        # It is reached only after the durable command row above exists, so retries
        # return that command/receipt instead of invoking the adapter again.
        result = adapter.submit(plan=plan, review=json.loads(str(review["review_json"])))
        action_executed = result.get("action_executed") is True
        requested_status = str(result.get("verification_status") or "SUBMISSION_UNVERIFIED")
        if not action_executed:
            final_status = "FAILED_SAFELY"
        elif requested_status == "VERIFIED" and self._verified_success_evidence(result):
            final_status = "VERIFIED"
        elif requested_status == "BLOCKED":
            final_status = "BLOCKED"
        elif requested_status == "FAILED_SAFELY":
            final_status = "FAILED_SAFELY"
        else:
            # A click, DOM mutation, or ambiguous navigation is never proof.
            final_status = "SUBMISSION_UNVERIFIED"

        success_evidence = _safe_evidence(dict(result.get("success_evidence") or {}))
        answers_digest = _sha(plan.get("answers") or [])
        chain_digest = self._event_chain_digest(str(session["session_id"]))
        receipt_snapshot = {
            "application_id": review["application_id"],
            "plan_id": review["plan_id"],
            "review_id": review_id,
            "session_id": review["session_id"],
            "command_id": command_id,
            "provider": plan_record["provider"],
            "submitted_at": result.get("submitted_at") or _now(),
            "submission_url": result.get("submission_url"),
            "provider_application_id": result.get("provider_application_id"),
            "resume_artifact_id": plan["resume"]["artifact_id"],
            "resume_sha256": plan["resume"]["artifact_sha256"],
            "answers_digest": answers_digest,
            "execution_chain_digest": chain_digest,
            "verification_status": final_status,
            "success_evidence": success_evidence,
        }
        receipt_digest = _sha(receipt_snapshot)
        receipt_id = "submission-receipt-" + receipt_digest[:32]
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO application_submission_receipts(
                       receipt_id,application_id,plan_id,session_id,review_id,command_id,
                       provider,submitted_at,submission_url,provider_application_id,
                       resume_artifact_id,resume_sha256,answers_digest,execution_chain_digest,
                       verification_status,success_evidence_json,receipt_json,receipt_digest,created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    receipt_id,
                    review["application_id"],
                    review["plan_id"],
                    review["session_id"],
                    review_id,
                    command_id,
                    plan_record["provider"],
                    receipt_snapshot["submitted_at"],
                    receipt_snapshot["submission_url"],
                    receipt_snapshot["provider_application_id"],
                    receipt_snapshot["resume_artifact_id"],
                    receipt_snapshot["resume_sha256"],
                    answers_digest,
                    chain_digest,
                    final_status,
                    canonical_json(success_evidence),
                    canonical_json(receipt_snapshot),
                    receipt_digest,
                    _now(),
                ),
            )
            connection.execute(
                "UPDATE final_submit_commands SET state=?,completed_at=? WHERE command_id=?",
                (final_status, _now(), command_id),
            )
        session = self._transition(session, final_status)
        self._record_event(
            session=session,
            event_type=final_status,
            replay_identity=f"{command_id}:outcome:{receipt_digest}",
            evidence={
                "receipt_id": receipt_id,
                "receipt_digest": receipt_digest,
                "verification_status": final_status,
                "success_evidence": success_evidence,
            },
        )
        return self._receipt_for_command(command_id) or {
            "receipt_id": receipt_id,
            "verification_status": final_status,
        }
