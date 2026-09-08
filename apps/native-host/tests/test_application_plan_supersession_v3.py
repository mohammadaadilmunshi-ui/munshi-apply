from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService


def _helpers():
    path = Path(__file__).resolve().parent / "test_application_plan_handoff_v2.py"
    spec = importlib.util.spec_from_file_location("supersession_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _helpers()


def _waiting_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")
    consumer, database = H._consumer(tmp_path)
    prior = H._plan()
    body, headers = H._signed(H._envelope(plan=prior))
    assert consumer.accept(body, headers, now=1000).accepted
    service = CompleteApplicationLoopService(
        database, tenant_id="tenant-a", user_id="member-a"
    )
    session = service.start_session(plan_id=str(prior["plan_id"]))
    queue = DurablePreparationQueue(database)
    job = queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    checkpoint = {"checkpoint_id": "checkpoint-runtime-1", "page_id": "page-runtime-1"}
    task = service._resolution_task(
        session=service._session(session.session_id),
        checkpoint=checkpoint,
        unresolved={
            "question_key": "first_name",
            "control_id": "first_name",
            "question": "First name",
            "semantic_type": "text",
            "sensitivity": "NORMAL",
            "reason": "Required answer is unresolved",
        },
    )
    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_sessions
               SET state='NEEDS_INPUT',browser_form_digest=?,checkpoint_id=?
               WHERE session_id=?""",
            ("f" * 64, checkpoint["checkpoint_id"], session.session_id),
        )
        connection.execute(
            "UPDATE applications SET status='NEEDS_INPUT' WHERE application_id=?",
            (session.application_id,),
        )
        connection.execute(
            "UPDATE complete_application_prepare_jobs SET state='WAITING_INPUT' WHERE job_id=?",
            (job["job_id"],),
        )
    return consumer, database, queue, prior, session, job, task


def _replacement_envelope(prior, session, task, *, form_digest: str = "f" * 64):
    replacement = H._plan(
        plan_id="application-plan-2",
        idempotency_key="plan-key-2",
        answers=[
            {
                "question_key": str(task.group_key),
                "normalized_question": str(task.question),
                "sensitivity_class": "NORMAL",
                "execution_value": "Aadil",
                "autofill_allowed": True,
            }
        ],
    )
    supersession = {
        "version": "munshi-application-plan-supersession-v1",
        "prior_plan_id": str(prior["plan_id"]),
        "prior_plan_digest": str(prior["plan_digest"]),
        "replacement_plan_id": str(replacement["plan_id"]),
        "replacement_plan_digest": str(replacement["plan_digest"]),
        "resolution_digest": "e" * 64,
        "session_id": session.session_id,
        "checkpoint_id": "checkpoint-runtime-1",
        "browser_form_digest": form_digest,
        "unresolved_questions": [
            {
                "question_key": str(task.group_key),
                "control_id": str(task.control_id),
                "question": str(task.question),
                "semantic_type": str(task.semantic_type),
                "sensitivity_class": "NORMAL",
            }
        ],
    }
    envelope = H._envelope(
        plan=replacement,
        handoff_id="plan-handoff-2",
        version="munshi-application-plan-handoff-v3",
        content_contract={
            "application_plan_version": "munshi-application-plan-v2",
            "receiver_min_version": 3,
            "receiver_max_version": 3,
        },
        supersession=supersession,
    )
    return replacement, envelope


def test_supersession_atomically_rebinds_same_waiting_session_and_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, queue, prior, session, job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    replacement, envelope = _replacement_envelope(prior, session, task)
    body, headers = H._signed(envelope, timestamp=1001)
    accepted = consumer.accept(body, headers, now=1001)
    replay = consumer.accept(body, headers, now=1001)
    assert accepted.accepted and not accepted.replayed
    assert accepted.resumed_session_id == session.session_id
    assert accepted.preparation_job_id == job["job_id"]
    assert replay.accepted and replay.replayed
    assert replay.resumed_session_id == session.session_id
    with database.connect() as connection:
        stored_session = connection.execute(
            "SELECT plan_id,state FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
        stored_job = connection.execute(
            "SELECT plan_id,state FROM complete_application_prepare_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()
        tasks = connection.execute(
            "SELECT status FROM resolution_tasks WHERE session_id=?",
            (session.session_id,),
        ).fetchall()
        lineage_count = connection.execute(
            "SELECT COUNT(*) FROM career_os_application_plan_supersessions"
        ).fetchone()[0]
        session_count = connection.execute(
            "SELECT COUNT(*) FROM complete_application_sessions"
        ).fetchone()[0]
        submit_count = connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0]
    assert stored_session["plan_id"] == replacement["plan_id"]
    assert stored_session["state"] == "NEEDS_INPUT"
    assert stored_job["plan_id"] == replacement["plan_id"]
    assert stored_job["state"] == "QUEUED"
    assert {row["status"] for row in tasks} == {"EXPIRED"}
    assert lineage_count == 1
    assert session_count == 1
    assert submit_count == 0
    assert queue.get(
        job_id=str(job["job_id"]), tenant_id="tenant-a", user_id="member-a"
    )["state"] == "QUEUED"


def test_supersession_rejects_stale_browser_context_without_partial_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, _queue, prior, session, _job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    replacement, envelope = _replacement_envelope(
        prior, session, task, form_digest="0" * 64
    )
    body, headers = H._signed(envelope, timestamp=1001)
    rejected = consumer.accept(body, headers, now=1001)
    assert not rejected.accepted
    assert "checkpoint" in str(rejected.error).lower()
    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM career_os_application_plans WHERE plan_id=?",
            (replacement["plan_id"],),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM career_os_application_plan_supersessions"
        ).fetchone()[0] == 0
        stored = connection.execute(
            "SELECT plan_id,state FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
    assert stored["plan_id"] == prior["plan_id"]
    assert stored["state"] == "NEEDS_INPUT"
