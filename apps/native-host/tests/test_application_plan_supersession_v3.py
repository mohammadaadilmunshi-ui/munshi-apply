from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from munshi_apply_native.application_plan_handoff_v2 import RuntimeQuestionBinding
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


def test_runtime_question_binding_accepts_only_value_free_observation() -> None:
    payload = {
        "question_key": "referral_source",
        "control_id": "source--source",
        "question": "How did you hear about us?",
        "semantic_type": "REFERRAL",
        "sensitivity_class": "NORMAL",
        "question_observation": {
            "label": "How did you hear about us?",
            "input_type": "text",
            "placeholder": "Search",
        },
    }
    assert RuntimeQuestionBinding.model_validate(payload).question_observation == payload[
        "question_observation"
    ]
    payload["question_observation"] = {"canonical_answer": "Indeed"}
    with pytest.raises(ValueError, match="candidate values or secrets"):
        RuntimeQuestionBinding.model_validate(payload)


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
    checkpoint = {
        "checkpoint_id": "checkpoint-runtime-1",
        "application_id": session.application_id,
        "sequence": 0,
        "state": "QUESTIONS",
        "page_id": "page-runtime-1",
        "page_fingerprint": "fixture-runtime-1",
        "completed_control_ids": [],
        "pending_control_ids": ["first_name"],
        "selected_resume_id": None,
        "selected_resume_sha256": None,
        "created_at": "2026-10-05T00:00:00+00:00",
    }
    service.checkpoints.save(checkpoint)
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
            """SELECT plan_id,state,continuation_pending,continuation_in_flight
                 FROM complete_application_prepare_jobs WHERE job_id=?""",
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
    assert stored_job["continuation_pending"] == 1
    assert stored_job["continuation_in_flight"] == 0
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


def test_supersession_allows_semantic_question_key_to_differ_from_browser_group_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, _queue, prior, session, job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    replacement, envelope = _replacement_envelope(prior, session, task)
    envelope["supersession"]["unresolved_questions"][0]["question_key"] = (
        "contact.first_name"
    )
    body, headers = H._signed(envelope, timestamp=1001)

    accepted = consumer.accept(body, headers, now=1001)

    assert accepted.accepted is True
    assert accepted.resumed_session_id == session.session_id
    assert accepted.preparation_job_id == job["job_id"]
    with database.connect() as connection:
        rebound = connection.execute(
            "SELECT plan_id,state FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
    assert rebound["plan_id"] == replacement["plan_id"]
    assert rebound["state"] == "NEEDS_INPUT"


def test_supersession_recovers_same_session_from_stale_failed_safely_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, queue, prior, session, job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='FAILED_SAFELY',
                   last_error='Hosted preparation plan is stale',
                   finished_at='2026-10-05T00:00:00+00:00',
                   attempt_count=2,
                   max_attempts=3
               WHERE job_id=?""",
            (job["job_id"],),
        )

    replacement, envelope = _replacement_envelope(prior, session, task)
    body, headers = H._signed(envelope, timestamp=1001)
    accepted = consumer.accept(body, headers, now=1001)

    assert accepted.accepted is True
    assert accepted.replayed is False
    assert accepted.resumed_session_id == session.session_id
    assert accepted.preparation_job_id == job["job_id"]

    with database.connect() as connection:
        stored_session = connection.execute(
            """SELECT plan_id,state
               FROM complete_application_sessions
               WHERE session_id=?""",
            (session.session_id,),
        ).fetchone()
        stored_job = connection.execute(
            """SELECT plan_id,state,attempt_count,max_attempts,last_error,
                      continuation_pending,continuation_in_flight,finished_at
               FROM complete_application_prepare_jobs
               WHERE job_id=?""",
            (job["job_id"],),
        ).fetchone()
        task_states = {
            row["status"]
            for row in connection.execute(
                "SELECT status FROM resolution_tasks WHERE session_id=?",
                (session.session_id,),
            ).fetchall()
        }
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
    assert stored_job["attempt_count"] == 2
    assert stored_job["max_attempts"] == 3
    assert stored_job["last_error"] is None
    assert stored_job["continuation_pending"] == 1
    assert stored_job["continuation_in_flight"] == 0
    assert stored_job["finished_at"] is None
    assert task_states == {"EXPIRED"}
    assert lineage_count == 1
    assert session_count == 1
    assert submit_count == 0
    assert queue.get(
        job_id=str(job["job_id"]),
        tenant_id="tenant-a",
        user_id="member-a",
    )["state"] == "QUEUED"


def test_supersession_rejects_unrelated_failed_safely_job_without_partial_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, _queue, prior, session, job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='FAILED_SAFELY',
                   last_error='Different preparation failure',
                   finished_at='2026-10-05T00:00:00+00:00'
               WHERE job_id=?""",
            (job["job_id"],),
        )

    replacement, envelope = _replacement_envelope(prior, session, task)
    body, headers = H._signed(envelope, timestamp=1001)
    rejected = consumer.accept(body, headers, now=1001)

    assert rejected.accepted is False
    assert "not safely resumable" in str(rejected.error)

    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM career_os_application_plans WHERE plan_id=?",
            (replacement["plan_id"],),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM career_os_application_plan_supersessions"
        ).fetchone()[0] == 0
        stored_session = connection.execute(
            """SELECT plan_id,state
               FROM complete_application_sessions
               WHERE session_id=?""",
            (session.session_id,),
        ).fetchone()
        stored_job = connection.execute(
            """SELECT plan_id,state,last_error
               FROM complete_application_prepare_jobs
               WHERE job_id=?""",
            (job["job_id"],),
        ).fetchone()

    assert stored_session["plan_id"] == prior["plan_id"]
    assert stored_session["state"] == "NEEDS_INPUT"
    assert stored_job["plan_id"] == prior["plan_id"]
    assert stored_job["state"] == "FAILED_SAFELY"
    assert stored_job["last_error"] == "Different preparation failure"



def test_signed_same_plan_replay_requeues_only_stale_failed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, queue, plan, session, job, _ = _waiting_fixture(
        tmp_path, monkeypatch
    )
    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='FAILED_SAFELY',
                   last_error='Hosted preparation plan is stale',
                   attempt_count=2,max_attempts=3,
                   finished_at='2026-10-05T00:00:00+00:00'
               WHERE job_id=?""",
            (job["job_id"],),
        )

    body, headers = H._signed(H._envelope(plan=plan), timestamp=1001)
    recovered = consumer.accept(body, headers, now=1001)
    repeated = consumer.accept(body, headers, now=1001)

    assert recovered.accepted is True
    assert recovered.replayed is True
    assert recovered.resumed_session_id == session.session_id
    assert recovered.preparation_job_id == job["job_id"]
    assert repeated.accepted is True
    assert repeated.replayed is True
    with database.connect() as connection:
        stored = connection.execute(
            """SELECT state,plan_id,attempt_count,max_attempts,last_error,
                      continuation_pending,continuation_in_flight,finished_at
               FROM complete_application_prepare_jobs WHERE job_id=?""",
            (job["job_id"],),
        ).fetchone()
        sess = connection.execute(
            "SELECT state,plan_id FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
        assert connection.execute(
            "SELECT COUNT(*) FROM complete_application_sessions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM complete_application_prepare_jobs"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM application_submission_receipts"
        ).fetchone()[0] == 0
    assert stored["state"] == "QUEUED"
    assert stored["plan_id"] == plan["plan_id"]
    assert stored["attempt_count"] == 2
    assert stored["max_attempts"] == 3
    assert stored["last_error"] is None
    assert stored["continuation_pending"] == 1
    assert stored["continuation_in_flight"] == 0
    assert stored["finished_at"] is None
    assert sess["state"] == "NEEDS_INPUT"
    assert sess["plan_id"] == plan["plan_id"]
    assert queue.get(
        job_id=str(job["job_id"]), tenant_id="tenant-a", user_id="member-a"
    )["state"] == "QUEUED"


@pytest.mark.parametrize(
    "error,attempts,session_state",
    [
        ("Other failure", 2, "NEEDS_INPUT"),
        ("Hosted preparation plan is stale", 3, "NEEDS_INPUT"),
        ("Hosted preparation plan is stale", 2, "READY_FOR_REVIEW"),
    ],
)
def test_same_plan_replay_does_not_resurrect_unrelated_or_exhausted_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: str,
    attempts: int,
    session_state: str,
) -> None:
    consumer, database, _, plan, session, job, _ = _waiting_fixture(
        tmp_path, monkeypatch
    )
    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='FAILED_SAFELY',last_error=?,
                   attempt_count=?,max_attempts=3
               WHERE job_id=?""",
            (error, attempts, job["job_id"]),
        )
        connection.execute(
            "UPDATE complete_application_sessions SET state=? WHERE session_id=?",
            (session_state, session.session_id),
        )
    body, headers = H._signed(H._envelope(plan=plan), timestamp=1001)
    result = consumer.accept(body, headers, now=1001)
    assert result.accepted is True and result.replayed is True
    assert result.preparation_job_id is None
    with database.connect() as connection:
        stored = connection.execute(
            """SELECT state,last_error,attempt_count
               FROM complete_application_prepare_jobs WHERE job_id=?""",
            (job["job_id"],),
        ).fetchone()
    assert (stored["state"],stored["last_error"],stored["attempt_count"]) == (
        "FAILED_SAFELY",error,attempts
    )



def test_committed_v3_supersession_replay_revives_only_original_stale_failed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, queue, prior, session, job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    replacement, envelope = _replacement_envelope(prior, session, task)
    body, headers = H._signed(envelope, timestamp=1001)
    accepted = consumer.accept(body, headers, now=1001)
    assert accepted.accepted and not accepted.replayed

    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='FAILED_SAFELY',
                   last_error='Hosted preparation plan is stale',
                   attempt_count=2,max_attempts=3,
                   continuation_pending=0,continuation_in_flight=0
               WHERE job_id=?""",
            (job["job_id"],),
        )

    replay = consumer.accept(body, headers, now=1001)
    assert replay.accepted and replay.replayed
    assert replay.resumed_session_id == session.session_id
    assert replay.preparation_job_id == job["job_id"]
    with database.connect() as connection:
        actual = connection.execute(
            """SELECT plan_id,state,last_error,attempt_count,max_attempts,
                      continuation_pending,continuation_in_flight
               FROM complete_application_prepare_jobs WHERE job_id=?""",
            (job["job_id"],),
        ).fetchone()
        assert connection.execute(
            "SELECT COUNT(*) FROM complete_application_sessions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM complete_application_prepare_jobs"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM application_submission_receipts"
        ).fetchone()[0] == 0
    assert actual["plan_id"] == replacement["plan_id"]
    assert actual["state"] == "QUEUED"
    assert actual["last_error"] is None
    assert actual["attempt_count"] == 2
    assert actual["max_attempts"] == 3
    assert actual["continuation_pending"] == 1
    assert actual["continuation_in_flight"] == 0
    assert queue.get(
        job_id=job["job_id"], tenant_id="tenant-a", user_id="member-a"
    )["state"] == "QUEUED"

def test_historical_open_task_is_reconciled_only_when_current_checkpoint_proves_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, queue, prior, session, job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    service = CompleteApplicationLoopService(
        database, tenant_id="tenant-a", user_id="member-a"
    )
    checkpoint_id = "checkpoint-runtime-2"
    service.checkpoints.save({
        "checkpoint_id": checkpoint_id,
        "application_id": session.application_id,
        "sequence": 1,
        "state": "QUESTIONS",
        "page_id": "page-runtime-2",
        "page_fingerprint": "fixture-runtime-2",
        "completed_control_ids": [],
        "pending_control_ids": [str(task.control_id)],
        "selected_resume_id": None,
        "selected_resume_sha256": None,
        "created_at": "2026-10-06T00:00:00+00:00",
    })
    with database.connect() as connection:
        connection.execute(
            "UPDATE complete_application_sessions SET checkpoint_id=? WHERE session_id=?",
            (checkpoint_id, session.session_id),
        )
    replacement, envelope = _replacement_envelope(prior, session, task)
    envelope["supersession"]["checkpoint_id"] = checkpoint_id
    body, headers = H._signed(envelope, timestamp=1001)
    result = consumer.accept(body, headers, now=1001)
    assert result.accepted and result.resumed_session_id == session.session_id
    assert result.preparation_job_id == job["job_id"]
    with database.connect() as connection:
        old = connection.execute(
            "SELECT status,checkpoint_id FROM resolution_tasks WHERE task_id=?",
            (task.task_id,),
        ).fetchone()
        assert (old["status"], old["checkpoint_id"]) == (
            "EXPIRED", "checkpoint-runtime-1"
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM complete_application_sessions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM complete_application_prepare_jobs"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0] == 0
    assert queue.get(
        job_id=job["job_id"], tenant_id="tenant-a", user_id="member-a"
    )["state"] == "QUEUED"


def test_historical_task_without_current_browser_pending_proof_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, database, _queue, prior, session, job, task = _waiting_fixture(
        tmp_path, monkeypatch
    )
    service = CompleteApplicationLoopService(
        database, tenant_id="tenant-a", user_id="member-a"
    )
    service.checkpoints.save({
        "checkpoint_id": "checkpoint-runtime-2",
        "application_id": session.application_id,
        "sequence": 1,
        "state": "QUESTIONS",
        "page_id": "page-runtime-2",
        "page_fingerprint": "fixture-runtime-2",
        "completed_control_ids": [],
        "pending_control_ids": ["different-control"],
        "selected_resume_id": None,
        "selected_resume_sha256": None,
        "created_at": "2026-10-06T00:00:00+00:00",
    })
    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_sessions
               SET checkpoint_id='checkpoint-runtime-2'
               WHERE session_id=?""",
            (session.session_id,),
        )
    _, envelope = _replacement_envelope(prior, session, task)
    envelope["supersession"]["checkpoint_id"] = "checkpoint-runtime-2"
    body, headers = H._signed(envelope, timestamp=1001)
    result = consumer.accept(body, headers, now=1001)
    assert result.accepted is False
    assert "browser checkpoint controls" in str(result.error)
    with database.connect() as connection:
        assert connection.execute(
            "SELECT status FROM resolution_tasks WHERE task_id=?", (task.task_id,)
        ).fetchone()[0] == "PENDING"
        assert connection.execute(
            "SELECT state FROM complete_application_prepare_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()[0] == "WAITING_INPUT"
