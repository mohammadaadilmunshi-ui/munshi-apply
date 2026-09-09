"""Default-off, inert consumer for signed synthetic Hunter submit commands.

This module accepts and durably claims only the exact synthetic submit authority
issued by Hunter. Acceptance and claiming are intentionally inert: neither path
creates a final submit command, changes application/session lifecycle state,
launches a browser, or performs any provider action.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .application_plan_handoff_v2 import _plan_digest_payload, _sha256_json
from .database import Database

SYNTHETIC_SUBMIT_COMMAND_ENV = "MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED"

COMMAND_VERSION = "munshi-synthetic-submit-command-v1"
COMMAND_PURPOSE = "SYNTHETIC_SUBMIT_COMMAND"
REVIEW_VERSION = "munshi-application-review-v2"
APPROVAL_VERSION = "munshi-application-review-approval-v2"
SUPPORTED_PROVIDER = "GREENHOUSE"
SENSITIVITY_CLASSES = frozenset(
    {"NORMAL", "PROTECTED", "SELF_ID", "CREDENTIAL", "POST_OFFER"}
)


def _enabled() -> bool:
    return str(os.getenv(SYNTHETIC_SUBMIT_COMMAND_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _canonical_command(value: dict[str, Any]) -> bytes:
    """Match Hunter application_submit_command_v1._canonical exactly."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _canonical_json(value: Any) -> str:
    """Match Hunter phase67_common.canonical_json exactly."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json_local(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _digest(value: Any, label: str) -> str:
    normalized = str(value or "").strip().casefold()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def _text(value: Any, label: str, maximum: int = 240) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} is required and must be at most {maximum} characters")
    return normalized


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a non-negative integer") from error
    if result < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return result


def _positive_int(value: Any, label: str) -> int:
    result = _non_negative_int(value, label)
    if result < 1:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _safe_review_fields(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Prepared review fields must be a list")
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("Prepared review field must be an object")
        sensitivity = str(raw.get("sensitivity_class") or "NORMAL").strip().upper()
        if sensitivity not in SENSITIVITY_CLASSES:
            raise ValueError("Prepared review field has an unsupported sensitivity class")
        display = raw.get("display_value")
        if sensitivity != "NORMAL":
            display = "[protected or sensitive value]"
        elif display is None and raw.get("execution_value") is not None:
            display = raw.get("execution_value")
        result.append(
            {
                "question_key": str(raw.get("question_key") or "").strip() or None,
                "question_family": str(raw.get("question_family") or "").strip() or None,
                "display_value": display,
                "sensitivity_class": sensitivity,
                "requires_review": bool(raw.get("requires_review")),
                "source": str(raw.get("source") or "").strip() or None,
            }
        )
    return result


class SubmitCommandEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["munshi-synthetic-submit-command-v1"]
    purpose: Literal["SYNTHETIC_SUBMIT_COMMAND"]
    command_id: str = Field(min_length=1, max_length=240)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    application_id: str = Field(min_length=1, max_length=240)
    plan_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=240)
    provider: Literal["GREENHOUSE"]
    review_id: str = Field(min_length=1, max_length=240)
    approval_id: str = Field(min_length=1, max_length=240)
    synthetic: Literal[True]
    submission_authority: Literal[True]
    fixture_job_id: int = Field(gt=0, strict=True)
    target_url: str = Field(min_length=1, max_length=4000)
    checkpoint_id: str = Field(min_length=1, max_length=240)
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prepared_package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    browser_form_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resume_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cover_letter_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    issued_at: int = Field(strict=True)
    expires_at: int = Field(strict=True)

    @field_validator(
        "command_id",
        "tenant_id",
        "user_id",
        "application_id",
        "plan_id",
        "session_id",
        "review_id",
        "approval_id",
        "checkpoint_id",
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("command identifiers cannot be blank")
        return normalized

    @model_validator(mode="after")
    def synthetic_target_and_expiry(self) -> "SubmitCommandEnvelope":
        target = urlparse(self.target_url)
        hostname = (target.hostname or "").casefold().rstrip(".")
        if (
            target.scheme.casefold() != "https"
            or not hostname
            or not hostname.endswith(".invalid")
            or target.username
            or target.password
            or target.fragment
        ):
            raise ValueError("synthetic target must be HTTPS on .invalid")
        if not 1 <= self.expires_at - self.issued_at <= 600:
            raise ValueError("synthetic command expiry must be 1..600 seconds")
        if not self.command_id.startswith("synthetic-submit-command-"):
            raise ValueError("synthetic submit command identity is invalid")
        if not self.review_id.startswith("review-v2-"):
            raise ValueError("Hunter review identity is invalid")
        if not self.approval_id.startswith("review-approval-"):
            raise ValueError("Hunter approval identity is invalid")
        return self


@dataclass(frozen=True)
class SubmitCommandResult:
    accepted: bool
    replayed: bool
    command_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SubmitCommandClaimResult:
    claimed: bool
    replayed: bool
    command_id: str | None = None
    error: str | None = None


class SyntheticSubmitCommandInbox:
    def __init__(self, database: Database, *, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("Synthetic submit command HMAC secret must be at least 32 characters")
        self.database = database
        self.secret = secret.encode("utf-8")

    def _parse_transport(
        self,
        body: bytes,
        *,
        body_sha256: str,
        signature: str,
    ) -> tuple[SubmitCommandEnvelope, str, str]:
        digest = hashlib.sha256(body).hexdigest()
        supplied_digest = _digest(body_sha256, "Submit command body digest")
        if not hmac.compare_digest(digest, supplied_digest):
            raise ValueError("submit command body digest mismatch")

        normalized_signature = str(signature or "").strip()
        if normalized_signature.casefold().startswith("sha256="):
            normalized_signature = normalized_signature.split("=", 1)[1]
        normalized_signature = _digest(normalized_signature, "Submit command signature")
        expected_signature = hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_signature, normalized_signature):
            raise PermissionError("invalid signature")

        try:
            payload = json.loads(body)
            envelope = SubmitCommandEnvelope.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as error:
            raise ValueError("malformed submit command") from error

        canonical = _canonical_command(envelope.model_dump(mode="json"))
        if not hmac.compare_digest(canonical, body):
            raise ValueError("submit command body is not canonical Hunter JSON")

        return envelope, digest, normalized_signature

    @staticmethod
    def _assert_fresh(envelope: SubmitCommandEnvelope, *, now: int) -> None:
        if isinstance(now, bool):
            raise ValueError("Submit command current time must be an integer")
        try:
            current = int(now)
        except (TypeError, ValueError) as error:
            raise ValueError("Submit command current time must be an integer") from error
        if not envelope.issued_at <= current <= envelope.expires_at:
            raise ValueError("expired submit command")

    @staticmethod
    def _prepared_package_locked(
        connection: sqlite3.Connection,
        *,
        envelope: SubmitCommandEnvelope,
        plan: dict[str, Any],
        session: sqlite3.Row,
    ) -> dict[str, Any]:
        row = connection.execute(
            """SELECT evidence_json
               FROM complete_application_execution_events
               WHERE session_id=? AND plan_id=? AND event_type='FORM_PREPARED'
               ORDER BY occurred_at DESC,event_id DESC
               LIMIT 1""",
            (envelope.session_id, envelope.plan_id),
        ).fetchone()
        if row is None:
            raise ValueError("current prepared browser evidence is unavailable")
        try:
            evidence = json.loads(str(row["evidence_json"]))
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("stored prepared browser evidence is malformed") from error
        if not isinstance(evidence, dict):
            raise ValueError("stored prepared browser evidence is malformed")

        form_digest = _digest(evidence.get("form_digest"), "Prepared browser form digest")
        resume_sha256 = _digest(evidence.get("resume_sha256"), "Prepared resume digest")
        unresolved_count = _non_negative_int(
            evidence.get("unresolved_count", 0),
            "Prepared unresolved field count",
        )
        validation_errors = [
            str(value)
            for value in list(evidence.get("validation_errors") or [])
            if str(value).strip()
        ]
        required_fields = _non_negative_int(
            evidence.get("required_fields", 0),
            "Prepared required field count",
        )
        completed_required_fields = _non_negative_int(
            evidence.get("completed_required_fields", 0),
            "Prepared completed field count",
        )
        if evidence.get("resume_uploaded") is not True:
            raise ValueError("prepared browser evidence does not verify resume upload")
        if unresolved_count:
            raise ValueError("prepared browser evidence still has unresolved inputs")
        if validation_errors:
            raise ValueError("prepared browser evidence still has validation errors")
        if completed_required_fields < required_fields:
            raise ValueError("prepared browser evidence has incomplete required fields")

        resume = plan.get("resume")
        if not isinstance(resume, dict):
            raise ValueError("accepted Application Plan resume binding is invalid")
        expected_resume = _digest(
            resume.get("artifact_sha256"),
            "Application Plan resume digest",
        )
        if resume_sha256 != expected_resume:
            raise ValueError("prepared resume does not match Application Plan")

        result: dict[str, Any] = {
            "application_id": envelope.application_id,
            "provider": envelope.provider,
            "destination_url": _text(
                session["current_url"],
                "Prepared destination URL",
                4000,
            ),
            "browser_form_digest": form_digest,
            "resume_sha256": resume_sha256,
            "required_fields": required_fields,
            "completed_required_fields": completed_required_fields,
            "unresolved_count": unresolved_count,
            "validation_errors": [],
            "checkpoint_id": _text(session["checkpoint_id"], "Prepared checkpoint id"),
            "review_fields": _safe_review_fields(evidence.get("review_fields")),
        }

        cover = plan.get("cover_letter")
        supplied_cover = evidence.get("cover_letter_sha256")
        if isinstance(cover, dict):
            expected_cover = _digest(
                cover.get("artifact_sha256"),
                "Application Plan cover-letter digest",
            )
            cover_sha256 = _digest(supplied_cover, "Prepared cover-letter digest")
            if evidence.get("cover_letter_uploaded") is not True:
                raise ValueError(
                    "prepared browser evidence does not verify cover-letter upload"
                )
            if cover_sha256 != expected_cover:
                raise ValueError("prepared cover letter does not match Application Plan")
            result["cover_letter_sha256"] = cover_sha256
        elif supplied_cover not in (None, ""):
            raise ValueError("prepared browser evidence has an unexpected cover letter")

        return result

    @staticmethod
    def _review_snapshot(
        *,
        envelope: SubmitCommandEnvelope,
        plan: dict[str, Any],
        prepared: dict[str, Any],
    ) -> dict[str, Any]:
        resume = plan.get("resume")
        job = plan.get("job")
        if not isinstance(resume, dict) or not isinstance(job, dict):
            raise ValueError("accepted Application Plan review bindings are incomplete")

        source_bindings = resume.get("source_bindings")
        if not isinstance(source_bindings, dict):
            source_bindings = {}
        job_binding = source_bindings.get("job")
        if not isinstance(job_binding, dict):
            job_binding = {}

        snapshot: dict[str, Any] = {
            "version": REVIEW_VERSION,
            "application_id": envelope.application_id,
            "plan_id": envelope.plan_id,
            "job": job,
            "provider": envelope.provider,
            "destination_url": prepared["destination_url"],
            "resume": {
                "filename": resume.get("filename"),
                "version_id": resume.get("version_id"),
                "artifact_id": resume.get("artifact_id"),
                "sha256": resume.get("artifact_sha256"),
                "truth_status": "BOUND",
                "job_binding": job_binding,
            },
            "application": {
                "required_fields": prepared["required_fields"],
                "completed_required_fields": prepared["completed_required_fields"],
                "unresolved": 0,
                "warnings": [],
            },
            "answers": prepared["review_fields"],
            "bindings": {
                "plan_digest": envelope.plan_digest,
                "prepared_package_digest": envelope.prepared_package_digest,
                "browser_form_digest": prepared["browser_form_digest"],
                "resume_artifact_sha256": prepared["resume_sha256"],
                "checkpoint_id": prepared["checkpoint_id"],
            },
            "submission_readiness": "READY_FOR_REVIEW",
            "submission_authority": False,
        }

        cover = plan.get("cover_letter")
        if isinstance(cover, dict):
            snapshot["cover_letter"] = {
                "filename": cover.get("filename"),
                "artifact_id": cover.get("artifact_id"),
                "sha256": cover.get("artifact_sha256"),
                "page_count": cover.get("page_count"),
                "truth_status": "BOUND",
            }
            snapshot["bindings"]["cover_letter_artifact_sha256"] = prepared[
                "cover_letter_sha256"
            ]
        return snapshot

    def _validate_bindings_locked(
        self,
        connection: sqlite3.Connection,
        envelope: SubmitCommandEnvelope,
    ) -> None:
        plan_row = connection.execute(
            """SELECT * FROM career_os_application_plans
               WHERE plan_id=? AND tenant_id=? AND user_id=?""",
            (envelope.plan_id, envelope.tenant_id, envelope.user_id),
        ).fetchone()
        session = connection.execute(
            """SELECT * FROM complete_application_sessions
               WHERE session_id=? AND application_id=? AND plan_id=?""",
            (envelope.session_id, envelope.application_id, envelope.plan_id),
        ).fetchone()
        application = connection.execute(
            "SELECT * FROM applications WHERE application_id=?",
            (envelope.application_id,),
        ).fetchone()
        if plan_row is None or session is None or application is None:
            raise ValueError("owned plan, application, or session is unavailable")

        if str(plan_row["acceptance_state"]) != "PLAN_ACCEPTED":
            raise ValueError("Application Plan is not accepted")
        if str(plan_row["application_id"]) != envelope.application_id:
            raise ValueError("Application Plan application binding changed")
        if str(plan_row["provider"]).upper() != envelope.provider:
            raise ValueError("Application Plan provider binding changed")
        if str(plan_row["plan_digest"]) != envelope.plan_digest:
            raise ValueError("Application Plan digest binding changed")

        try:
            plan = json.loads(str(plan_row["plan_json"]))
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("stored Application Plan is malformed") from error
        if not isinstance(plan, dict):
            raise ValueError("stored Application Plan is malformed")
        if _sha256_json(_plan_digest_payload(plan)) != str(plan_row["plan_digest"]):
            raise ValueError("stored Application Plan integrity failure")
        if plan.get("submission_authority") is not False:
            raise ValueError("accepted Application Plan unexpectedly carries submit authority")
        if plan.get("executable") is not True or plan.get("expected_state") != "READY_TO_APPLY":
            raise ValueError("accepted Application Plan is not execution-ready")
        if str(plan.get("application_id")) != envelope.application_id:
            raise ValueError("Application Plan payload application binding changed")
        if str(plan.get("plan_id")) != envelope.plan_id:
            raise ValueError("Application Plan payload identity changed")

        provider_policy = plan.get("provider_policy")
        if (
            not isinstance(provider_policy, dict)
            or str(provider_policy.get("provider") or "").upper() != envelope.provider
            or provider_policy.get("permitted") is not True
        ):
            raise ValueError("Application Plan provider policy is unavailable")

        job = plan.get("job")
        resume = plan.get("resume")
        if not isinstance(job, dict) or not isinstance(resume, dict):
            raise ValueError("Application Plan artifact or job binding is incomplete")
        if _positive_int(job.get("id"), "Application Plan job id") != envelope.fixture_job_id:
            raise ValueError("synthetic fixture job identity changed")
        if str(job.get("apply_url") or "") != envelope.target_url:
            raise ValueError("synthetic fixture destination changed")
        if _digest(resume.get("artifact_sha256"), "Application Plan resume digest") != (
            envelope.resume_sha256
        ):
            raise ValueError("Application Plan resume digest changed")

        cover = plan.get("cover_letter")
        if isinstance(cover, dict):
            if _digest(
                cover.get("artifact_sha256"),
                "Application Plan cover-letter digest",
            ) != envelope.cover_letter_sha256:
                raise ValueError("Application Plan cover-letter digest changed")
        elif envelope.cover_letter_sha256 is not None:
            raise ValueError("submit command contains an unexpected cover-letter digest")

        if str(session["provider"]).upper() != envelope.provider:
            raise ValueError("execution session provider changed")
        if str(session["state"]) != "READY_TO_SUBMIT":
            raise ValueError("execution session is not READY_TO_SUBMIT")
        if str(application["status"]) != "READY_TO_SUBMIT":
            raise ValueError("application is not READY_TO_SUBMIT")
        if str(session["current_url"] or "") != envelope.target_url:
            raise ValueError("execution session destination changed")
        if str(session["browser_form_digest"] or "") != envelope.browser_form_digest:
            raise ValueError("execution session browser form changed")
        if str(session["checkpoint_id"] or "") != envelope.checkpoint_id:
            raise ValueError("execution session checkpoint changed")

        checkpoint = connection.execute(
            """SELECT * FROM application_checkpoints
               WHERE checkpoint_id=? AND application_id=?""",
            (envelope.checkpoint_id, envelope.application_id),
        ).fetchone()
        if checkpoint is None:
            raise ValueError("execution checkpoint is unavailable")
        if str(checkpoint["selected_resume_sha256"] or "") != envelope.resume_sha256:
            raise ValueError("execution checkpoint resume binding changed")

        submit_rows = connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands WHERE session_id=?",
            (envelope.session_id,),
        ).fetchone()[0]
        receipt_rows = connection.execute(
            "SELECT COUNT(*) FROM application_submission_receipts WHERE session_id=?",
            (envelope.session_id,),
        ).fetchone()[0]
        if int(submit_rows) or int(receipt_rows):
            raise ValueError("execution session already has local submission authority or outcome")

        prepared = self._prepared_package_locked(
            connection,
            envelope=envelope,
            plan=plan,
            session=session,
        )
        if prepared["destination_url"] != envelope.target_url:
            raise ValueError("prepared package destination changed")
        if prepared["checkpoint_id"] != envelope.checkpoint_id:
            raise ValueError("prepared package checkpoint changed")
        if prepared["browser_form_digest"] != envelope.browser_form_digest:
            raise ValueError("prepared package browser form changed")
        if prepared["resume_sha256"] != envelope.resume_sha256:
            raise ValueError("prepared package resume changed")
        if prepared.get("cover_letter_sha256") != envelope.cover_letter_sha256:
            raise ValueError("prepared package cover letter changed")

        prepared_digest = _sha256_json_local(prepared)
        if prepared_digest != envelope.prepared_package_digest:
            raise ValueError("prepared package digest does not match Hunter authority")

        review_snapshot = self._review_snapshot(
            envelope=envelope,
            plan=plan,
            prepared=prepared,
        )
        review_digest = _sha256_json_local(review_snapshot)
        if review_digest != envelope.review_digest:
            raise ValueError("review digest does not match current Apply preparation")
        if envelope.review_id != "review-v2-" + review_digest[:32]:
            raise ValueError("review identity does not match current Apply preparation")

        approval_material = {
            "version": APPROVAL_VERSION,
            "review_id": envelope.review_id,
            "review_digest": review_digest,
            "plan_digest": envelope.plan_digest,
            "prepared_package_digest": prepared_digest,
            "browser_form_digest": envelope.browser_form_digest,
        }
        if _sha256_json_local(approval_material) != envelope.approval_digest:
            raise ValueError("approval digest does not match exact current review")

    def accept(
        self,
        body: bytes,
        *,
        body_sha256: str,
        signature: str,
        now: int,
    ) -> SubmitCommandResult:
        if not _enabled():
            return SubmitCommandResult(
                False,
                False,
                error="synthetic submit commands disabled",
            )

        try:
            envelope, digest, normalized_signature = self._parse_transport(
                body,
                body_sha256=body_sha256,
                signature=signature,
            )
            self._assert_fresh(envelope, now=now)
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                prior = connection.execute(
                    """SELECT body_sha256,signature
                       FROM synthetic_submit_command_inbox
                       WHERE command_id=?""",
                    (envelope.command_id,),
                ).fetchone()
                if prior is not None:
                    if (
                        str(prior["body_sha256"]) == digest
                        and hmac.compare_digest(
                            str(prior["signature"]),
                            normalized_signature,
                        )
                    ):
                        return SubmitCommandResult(True, True, envelope.command_id)
                    return SubmitCommandResult(
                        False,
                        False,
                        error="submit command replay conflict",
                    )

                approval_conflict = connection.execute(
                    """SELECT command_id,body_sha256
                       FROM synthetic_submit_command_inbox
                       WHERE tenant_id=? AND user_id=? AND approval_id=?""",
                    (
                        envelope.tenant_id,
                        envelope.user_id,
                        envelope.approval_id,
                    ),
                ).fetchone()
                if approval_conflict is not None:
                    return SubmitCommandResult(
                        False,
                        False,
                        error="submit approval is already bound to another command",
                    )

                self._validate_bindings_locked(connection, envelope)
                connection.execute(
                    """INSERT INTO synthetic_submit_command_inbox(
                           command_id,tenant_id,user_id,application_id,plan_id,session_id,
                           provider,review_id,approval_id,fixture_job_id,target_url,
                           checkpoint_id,review_digest,approval_digest,plan_digest,
                           prepared_package_digest,browser_form_digest,resume_sha256,
                           cover_letter_sha256,issued_at,expires_at,envelope_json,
                           body_sha256,signature,acceptance_state,accepted_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        envelope.command_id,
                        envelope.tenant_id,
                        envelope.user_id,
                        envelope.application_id,
                        envelope.plan_id,
                        envelope.session_id,
                        envelope.provider,
                        envelope.review_id,
                        envelope.approval_id,
                        envelope.fixture_job_id,
                        envelope.target_url,
                        envelope.checkpoint_id,
                        envelope.review_digest,
                        envelope.approval_digest,
                        envelope.plan_digest,
                        envelope.prepared_package_digest,
                        envelope.browser_form_digest,
                        envelope.resume_sha256,
                        envelope.cover_letter_sha256,
                        envelope.issued_at,
                        envelope.expires_at,
                        body.decode("utf-8"),
                        digest,
                        normalized_signature,
                        "COMMAND_ACCEPTED",
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except PermissionError as error:
            return SubmitCommandResult(False, False, error=str(error))
        except (UnicodeDecodeError, ValueError, sqlite3.IntegrityError) as error:
            return SubmitCommandResult(False, False, error=str(error))
        return SubmitCommandResult(True, False, envelope.command_id)

    def claim(self, command_id: str, *, now: int) -> SubmitCommandClaimResult:
        if not _enabled():
            return SubmitCommandClaimResult(
                False,
                False,
                error="synthetic submit commands disabled",
            )
        try:
            resolved_command_id = _text(command_id, "Synthetic submit command id")
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM synthetic_submit_command_inbox WHERE command_id=?",
                    (resolved_command_id,),
                ).fetchone()
                if row is None:
                    return SubmitCommandClaimResult(
                        False,
                        False,
                        error="synthetic submit command was not accepted",
                    )

                body = str(row["envelope_json"]).encode("utf-8")
                envelope, digest, normalized_signature = self._parse_transport(
                    body,
                    body_sha256=str(row["body_sha256"]),
                    signature=str(row["signature"]),
                )
                if envelope.command_id != resolved_command_id:
                    raise ValueError("stored submit command identity is inconsistent")
                if digest != str(row["body_sha256"]):
                    raise ValueError("stored submit command body digest is inconsistent")
                if not hmac.compare_digest(
                    normalized_signature,
                    str(row["signature"]),
                ):
                    raise ValueError("stored submit command signature is inconsistent")
                self._assert_fresh(envelope, now=now)

                prior_claim = connection.execute(
                    """SELECT body_sha256
                       FROM synthetic_submit_command_claims
                       WHERE command_id=?""",
                    (resolved_command_id,),
                ).fetchone()
                if prior_claim is not None:
                    if str(prior_claim["body_sha256"]) != digest:
                        raise ValueError(
                            "synthetic submit command claim conflicts with command body"
                        )
                    return SubmitCommandClaimResult(
                        False,
                        True,
                        resolved_command_id,
                        error="synthetic submit command already claimed",
                    )

                self._validate_bindings_locked(connection, envelope)
                connection.execute(
                    """INSERT INTO synthetic_submit_command_claims(
                           command_id,body_sha256,claimed_at
                       ) VALUES (?,?,?)""",
                    (
                        resolved_command_id,
                        digest,
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except PermissionError as error:
            return SubmitCommandClaimResult(False, False, error=str(error))
        except (UnicodeDecodeError, ValueError, sqlite3.IntegrityError) as error:
            return SubmitCommandClaimResult(False, False, error=str(error))
        return SubmitCommandClaimResult(True, False, resolved_command_id)
