from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from typing import Any

import pytest
from test_application_plan_handoff_v2 import _consumer, _envelope, _plan, _signed

from munshi_apply_native.synthetic_submit_command_inbox import SyntheticSubmitCommandInbox

SECRET = "synthetic-submit-command-secret-which-is-long-enough"  # noqa: S105
TARGET = "https://synthetic.greenhouse.invalid/jobs/41"
REVIEW_VERSION = "munshi-application-review-v2"
APPROVAL_VERSION = "munshi-application-review-approval-v2"


def _canonical(value: Any, *, ensure_ascii: bool = False) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
    )


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _recalculate_plan_digest(plan: dict[str, Any]) -> None:
    payload = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "idempotency_key", "plan_digest", "created_at"}
    }
    plan["plan_digest"] = _digest_json(payload)


def _ready(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")

    plan = _plan()
    plan["job"]["job_url"] = TARGET
    plan["job"]["apply_url"] = TARGET
    _recalculate_plan_digest(plan)

    consumer, database = _consumer(tmp_path)
    handoff_body, handoff_headers = _signed(_envelope(plan=plan))
    assert consumer.accept(handoff_body, handoff_headers, now=1000).accepted

    form_digest = hashlib.sha256(b"fixture-form").hexdigest()
    review_fields = [
        {
            "question_key": "portfolio",
            "question_family": None,
            "display_value": "https://example.test/portfolio",
            "sensitivity_class": "NORMAL",
            "requires_review": False,
            "source": "FIXTURE",
        }
    ]
    prepared = {
        "application_id": "application-1",
        "provider": "GREENHOUSE",
        "destination_url": TARGET,
        "browser_form_digest": form_digest,
        "resume_sha256": plan["resume"]["artifact_sha256"],
        "required_fields": 2,
        "completed_required_fields": 2,
        "unresolved_count": 0,
        "validation_errors": [],
        "checkpoint_id": "checkpoint-1",
        "review_fields": review_fields,
    }
    prepared_digest = _digest_json(prepared)

    resume = plan["resume"]
    source_bindings = resume.get("source_bindings")
    job_binding = (
        source_bindings.get("job")
        if isinstance(source_bindings, dict)
        and isinstance(source_bindings.get("job"), dict)
        else {}
    )
    review_snapshot = {
        "version": REVIEW_VERSION,
        "application_id": "application-1",
        "plan_id": "application-plan-1",
        "job": plan["job"],
        "provider": "GREENHOUSE",
        "destination_url": TARGET,
        "resume": {
            "filename": resume.get("filename"),
            "version_id": resume.get("version_id"),
            "artifact_id": resume.get("artifact_id"),
            "sha256": resume.get("artifact_sha256"),
            "truth_status": "BOUND",
            "job_binding": job_binding,
        },
        "application": {
            "required_fields": 2,
            "completed_required_fields": 2,
            "unresolved": 0,
            "warnings": [],
        },
        "answers": review_fields,
        "bindings": {
            "plan_digest": plan["plan_digest"],
            "prepared_package_digest": prepared_digest,
            "browser_form_digest": form_digest,
            "resume_artifact_sha256": resume["artifact_sha256"],
            "checkpoint_id": "checkpoint-1",
        },
        "submission_readiness": "READY_FOR_REVIEW",
        "submission_authority": False,
    }
    review_digest = _digest_json(review_snapshot)
    review_id = "review-v2-" + review_digest[:32]
    approval_material = {
        "version": APPROVAL_VERSION,
        "review_id": review_id,
        "review_digest": review_digest,
        "plan_digest": plan["plan_digest"],
        "prepared_package_digest": prepared_digest,
        "browser_form_digest": form_digest,
    }
    approval_digest = _digest_json(approval_material)

    evidence = {
        "required_fields": 2,
        "completed_required_fields": 2,
        "unresolved_count": 0,
        "validation_errors": [],
        "resume_uploaded": True,
        "resume_sha256": resume["artifact_sha256"],
        "form_digest": form_digest,
        "review_fields": review_fields,
    }

    with database.connect() as connection:
        connection.execute(
            """INSERT INTO applications(
                   application_id,status,created_at,updated_at
               ) VALUES ('application-1','READY_TO_SUBMIT','now','now')"""
        )
        connection.execute(
            """INSERT INTO complete_application_sessions(
                   session_id,application_id,plan_id,provider,state,current_url,
                   browser_form_digest,checkpoint_id,created_at,updated_at
               ) VALUES (
                   'session-1','application-1','application-plan-1','GREENHOUSE',
                   'READY_TO_SUBMIT',?,?,?,'now','now'
               )""",
            (TARGET, form_digest, "checkpoint-1"),
        )
        connection.execute(
            """INSERT INTO application_checkpoints(
                   checkpoint_id,application_id,sequence,state,page_id,page_fingerprint,
                   completed_control_ids_json,pending_control_ids_json,
                   selected_resume_id,selected_resume_sha256,created_at
               ) VALUES (
                   'checkpoint-1','application-1',1,'QUESTIONS','application-form',
                   'fixture-page','{"items":["resume","portfolio"]}','{"items":[]}',
                   'resume-artifact-1',?,'now'
               )""",
            (resume["artifact_sha256"],),
        )
        connection.execute(
            """INSERT INTO complete_application_execution_events(
                   event_id,application_id,plan_id,session_id,provider,event_type,
                   replay_identity,evidence_json,checkpoint_json,occurred_at
               ) VALUES (
                   'event-form-prepared','application-1','application-plan-1',
                   'session-1','GREENHOUSE','FORM_PREPARED',
                   'session-1:form-prepared:fixture',?,NULL,'now'
               )""",
            (_canonical(evidence),),
        )

    fields = {
        "form": form_digest,
        "prepared": prepared_digest,
        "review": review_digest,
        "review_id": review_id,
        "approval": approval_digest,
    }
    return database, plan, fields


def _command(plan, fields, **changes):
    command = {
        "version": "munshi-synthetic-submit-command-v1",
        "purpose": "SYNTHETIC_SUBMIT_COMMAND",
        "command_id": "synthetic-submit-command-1",
        "tenant_id": "tenant-a",
        "user_id": "member-a",
        "application_id": "application-1",
        "plan_id": "application-plan-1",
        "session_id": "session-1",
        "provider": "GREENHOUSE",
        "review_id": fields["review_id"],
        "approval_id": "review-approval-1",
        "synthetic": True,
        "submission_authority": True,
        "fixture_job_id": 41,
        "target_url": TARGET,
        "checkpoint_id": "checkpoint-1",
        "review_digest": fields["review"],
        "approval_digest": fields["approval"],
        "plan_digest": plan["plan_digest"],
        "prepared_package_digest": fields["prepared"],
        "browser_form_digest": fields["form"],
        "resume_sha256": plan["resume"]["artifact_sha256"],
        "cover_letter_sha256": None,
        "issued_at": 1000,
        "expires_at": 1300,
    }
    command.update(changes)
    body = _canonical(command, ensure_ascii=True).encode("utf-8")
    body_sha256 = hashlib.sha256(body).hexdigest()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, body_sha256, signature


def _counts(database):
    with database.connect() as connection:
        return {
            "inbox": connection.execute(
                "SELECT COUNT(*) FROM synthetic_submit_command_inbox"
            ).fetchone()[0],
            "claims": connection.execute(
                "SELECT COUNT(*) FROM synthetic_submit_command_claims"
            ).fetchone()[0],
            "local_reviews": connection.execute(
                "SELECT COUNT(*) FROM final_application_reviews"
            ).fetchone()[0],
            "submits": connection.execute(
                "SELECT COUNT(*) FROM final_submit_commands"
            ).fetchone()[0],
            "receipts": connection.execute(
                "SELECT COUNT(*) FROM application_submission_receipts"
            ).fetchone()[0],
        }


def test_signed_command_default_off_then_inert_and_exactly_replayed(
    tmp_path,
    monkeypatch,
):
    database, plan, fields = _ready(tmp_path, monkeypatch)
    inbox = SyntheticSubmitCommandInbox(database, secret=SECRET)
    body, body_sha256, signature = _command(plan, fields)

    result = inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature,
        now=1100,
    )
    assert not result.accepted
    assert result.error == "synthetic submit commands disabled"

    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED", "true")
    first = inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature,
        now=1100,
    )
    second = inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature.upper(),
        now=1100,
    )

    assert first.accepted and not first.replayed
    assert second.accepted and second.replayed
    assert _counts(database) == {
        "inbox": 1,
        "claims": 0,
        "local_reviews": 0,
        "submits": 0,
        "receipts": 0,
    }
    with database.connect() as connection:
        assert connection.execute(
            "SELECT state FROM complete_application_sessions"
        ).fetchone()[0] == "READY_TO_SUBMIT"


def test_command_rejects_transport_expiry_noncanonical_and_real_target(
    tmp_path,
    monkeypatch,
):
    database, plan, fields = _ready(tmp_path, monkeypatch)
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED", "true")
    inbox = SyntheticSubmitCommandInbox(database, secret=SECRET)
    body, body_sha256, signature = _command(plan, fields)

    assert (
        inbox.accept(
            body,
            body_sha256="0" * 64,
            signature=signature,
            now=1100,
        ).error
        == "submit command body digest mismatch"
    )
    assert (
        inbox.accept(
            body,
            body_sha256=body_sha256,
            signature="0" * 64,
            now=1100,
        ).error
        == "invalid signature"
    )
    assert (
        inbox.accept(
            body,
            body_sha256=body_sha256,
            signature=signature,
            now=1301,
        ).error
        == "expired submit command"
    )

    payload = json.loads(body)
    pretty = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    pretty_digest = hashlib.sha256(pretty).hexdigest()
    pretty_signature = hmac.new(SECRET.encode(), pretty, hashlib.sha256).hexdigest()
    assert "not canonical" in (
        inbox.accept(
            pretty,
            body_sha256=pretty_digest,
            signature=pretty_signature,
            now=1100,
        ).error
        or ""
    )

    real_body, real_digest, real_signature = _command(
        plan,
        fields,
        target_url="https://boards.greenhouse.io/example/jobs/41",
    )
    assert not inbox.accept(
        real_body,
        body_sha256=real_digest,
        signature=real_signature,
        now=1100,
    ).accepted
    assert _counts(database)["inbox"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prepared_package_digest", "1" * 64),
        ("review_digest", "2" * 64),
        ("approval_digest", "3" * 64),
        ("plan_digest", "4" * 64),
        ("browser_form_digest", "5" * 64),
        ("resume_sha256", "6" * 64),
    ],
)
def test_command_rejects_authority_digest_drift(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    database, plan, fields = _ready(tmp_path, monkeypatch)
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED", "true")
    inbox = SyntheticSubmitCommandInbox(database, secret=SECRET)
    body, body_sha256, signature = _command(plan, fields, **{field: value})

    result = inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature,
        now=1100,
    )

    assert not result.accepted
    assert _counts(database)["inbox"] == 0


def test_command_replay_conflict_and_approval_single_binding(tmp_path, monkeypatch):
    database, plan, fields = _ready(tmp_path, monkeypatch)
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED", "true")
    inbox = SyntheticSubmitCommandInbox(database, secret=SECRET)
    body, body_sha256, signature = _command(plan, fields)
    assert inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature,
        now=1100,
    ).accepted

    altered_body, altered_digest, altered_signature = _command(
        plan,
        fields,
        expires_at=1299,
    )
    conflict = inbox.accept(
        altered_body,
        body_sha256=altered_digest,
        signature=altered_signature,
        now=1100,
    )
    assert not conflict.accepted
    assert conflict.error == "submit command replay conflict"

    second_body, second_digest, second_signature = _command(
        plan,
        fields,
        command_id="synthetic-submit-command-2",
    )
    second = inbox.accept(
        second_body,
        body_sha256=second_digest,
        signature=second_signature,
        now=1100,
    )
    assert not second.accepted
    assert second.error == "submit approval is already bound to another command"
    assert _counts(database)["inbox"] == 1


def test_claim_is_durable_exactly_once_and_remains_inert(tmp_path, monkeypatch):
    database, plan, fields = _ready(tmp_path, monkeypatch)
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED", "true")
    inbox = SyntheticSubmitCommandInbox(database, secret=SECRET)
    body, body_sha256, signature = _command(plan, fields)
    accepted = inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature,
        now=1100,
    )
    assert accepted.accepted

    first = inbox.claim("synthetic-submit-command-1", now=1101)
    second = inbox.claim("synthetic-submit-command-1", now=1102)

    assert first.claimed and not first.replayed
    assert not second.claimed and second.replayed
    assert second.error == "synthetic submit command already claimed"
    assert _counts(database) == {
        "inbox": 1,
        "claims": 1,
        "local_reviews": 0,
        "submits": 0,
        "receipts": 0,
    }
    with database.connect() as connection:
        assert connection.execute(
            "SELECT state FROM complete_application_sessions"
        ).fetchone()[0] == "READY_TO_SUBMIT"

    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as connection:
            connection.execute(
                """UPDATE synthetic_submit_command_inbox
                   SET acceptance_state='COMMAND_ACCEPTED'
                   WHERE command_id='synthetic-submit-command-1'"""
            )

    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as connection:
            connection.execute(
                """DELETE FROM synthetic_submit_command_claims
                   WHERE command_id='synthetic-submit-command-1'"""
            )


def test_claim_revalidates_current_browser_binding_before_authority_use(
    tmp_path,
    monkeypatch,
):
    database, plan, fields = _ready(tmp_path, monkeypatch)
    monkeypatch.setenv("MUNSHI_APPLY_SYNTHETIC_SUBMIT_COMMAND_ENABLED", "true")
    inbox = SyntheticSubmitCommandInbox(database, secret=SECRET)
    body, body_sha256, signature = _command(plan, fields)
    assert inbox.accept(
        body,
        body_sha256=body_sha256,
        signature=signature,
        now=1100,
    ).accepted

    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_sessions
               SET checkpoint_id='checkpoint-drifted'
               WHERE session_id='session-1'"""
        )

    claim = inbox.claim("synthetic-submit-command-1", now=1101)
    assert not claim.claimed
    assert not claim.replayed
    assert "checkpoint changed" in (claim.error or "")
    assert _counts(database)["claims"] == 0
    assert _counts(database)["submits"] == 0
