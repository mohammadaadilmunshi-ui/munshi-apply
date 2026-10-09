from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_application_plan_handoff_v2 import _consumer, _envelope, _signed

from munshi_apply_native.background_prepare_queue import (
    DurablePreparationQueue,
    DurablePreparationWorker,
)
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService


@pytest.fixture
def queued(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")
    consumer, db = _consumer(tmp_path)
    body, headers = _signed(_envelope())
    assert consumer.accept(body, headers, now=1000).accepted

    service = CompleteApplicationLoopService(db, tenant_id="tenant-a", user_id="member-a")
    session = service.start_session(plan_id="application-plan-1")
    queue = DurablePreparationQueue(db)
    job = queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-08T03:00:00+00:00",
    )
    return db, service, session, queue, job


def test_enqueue_is_idempotent_and_owner_scoped(queued):
    _, _, session, queue, first = queued
    second = queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-08T03:00:01+00:00",
    )
    assert second["job_id"] == first["job_id"]
    assert second["state"] == "QUEUED"

    with pytest.raises(LookupError):
        queue.get(
            job_id=first["job_id"],
            tenant_id="tenant-a",
            user_id="somebody-else",
        )


def test_atomic_claim_has_single_owner_and_heartbeat_extends_lease(queued):
    _, _, _, queue, job = queued
    first = queue.claim_next(
        worker_id="worker-a",
        lease_seconds=30,
        now="2026-09-08T03:00:00+00:00",
    )
    assert first is not None
    assert first["job_id"] == job["job_id"]
    assert first["state"] == "RUNNING"
    assert first["attempt_count"] == 1
    assert (
        queue.claim_next(
            worker_id="worker-b",
            lease_seconds=30,
            now="2026-09-08T03:00:01+00:00",
        )
        is None
    )

    heartbeat = queue.heartbeat(
        job_id=job["job_id"],
        worker_id="worker-a",
        lease_seconds=60,
        now="2026-09-08T03:00:10+00:00",
    )
    assert heartbeat["heartbeat_at"] == "2026-09-08T03:00:10+00:00"
    assert heartbeat["lease_expires_at"] == "2026-09-08T03:01:10+00:00"

    with pytest.raises(RuntimeError, match="owned"):
        queue.heartbeat(
            job_id=job["job_id"],
            worker_id="worker-b",
            now="2026-09-08T03:00:11+00:00",
        )


def test_expired_pre_submit_lease_is_recovered_with_bounded_attempts(queued):
    _, _, _, queue, job = queued
    assert queue.claim_next(
        worker_id="worker-a",
        lease_seconds=10,
        now="2026-09-08T03:00:00+00:00",
    )
    recovered = queue.claim_next(
        worker_id="worker-b",
        lease_seconds=10,
        now="2026-09-08T03:00:11+00:00",
    )
    assert recovered is not None
    assert recovered["job_id"] == job["job_id"]
    assert recovered["lease_owner"] == "worker-b"
    assert recovered["attempt_count"] == 2
    assert "expired pre-submit worker lease" in recovered["last_error"]

    third = queue.claim_next(
        worker_id="worker-c",
        lease_seconds=10,
        now="2026-09-08T03:00:22+00:00",
    )
    assert third is not None
    assert third["attempt_count"] == 3

    assert (
        queue.claim_next(
            worker_id="worker-d",
            lease_seconds=10,
            now="2026-09-08T03:00:33+00:00",
        )
        is None
    )
    stored = queue.get(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
    )
    assert stored["state"] == "FAILED_SAFELY"


def test_cancel_queued_is_terminal_and_never_claimed(queued):
    _, _, _, queue, job = queued
    cancelled = queue.request_cancel(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-08T03:00:02+00:00",
    )
    assert cancelled["state"] == "CANCELLED"
    assert (
        queue.claim_next(
            worker_id="worker-a",
            now="2026-09-08T03:00:03+00:00",
        )
        is None
    )


def test_cancel_running_is_cooperative_at_preparation_boundary(queued):
    _, _, _, queue, job = queued
    assert queue.claim_next(
        worker_id="worker-a",
        now="2026-09-08T03:00:00+00:00",
    )
    requested = queue.request_cancel(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-08T03:00:01+00:00",
    )
    assert requested["state"] == "RUNNING"
    assert requested["cancel_requested_at"] is not None

    finished = queue.finish(
        job_id=job["job_id"],
        worker_id="worker-a",
        session_state="READY_FOR_REVIEW",
        now="2026-09-08T03:00:02+00:00",
    )
    assert finished["state"] == "CANCELLED"


def test_needs_input_can_requeue_after_resolution_without_spending_retry_budget(queued):
    _, _, session, queue, job = queued
    first = queue.claim_next(
        worker_id="worker-a",
        now="2026-09-08T03:00:00+00:00",
    )
    assert first is not None
    assert first["attempt_count"] == 1

    waiting = queue.finish(
        job_id=job["job_id"],
        worker_id="worker-a",
        session_state="NEEDS_INPUT",
        now="2026-09-08T03:00:01+00:00",
    )
    assert waiting["state"] == "WAITING_INPUT"
    assert waiting["attempt_count"] == 1

    requeued = queue.requeue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-08T03:00:02+00:00",
    )
    assert requeued is not None
    assert requeued["state"] == "QUEUED"
    assert requeued["continuation_pending"] == 1

    continuation = queue.claim_next(
        worker_id="worker-b",
        now="2026-09-08T03:00:03+00:00",
    )
    assert continuation is not None
    assert continuation["continuation_in_flight"] == 1
    assert continuation["attempt_count"] == 2

    finished = queue.finish(
        job_id=job["job_id"],
        worker_id="worker-b",
        session_state="READY_FOR_REVIEW",
        now="2026-09-08T03:00:04+00:00",
    )
    assert finished["state"] == "READY_FOR_REVIEW"
    assert finished["attempt_count"] == 1
    assert finished["continuation_count"] == 1
    assert finished["continuation_in_flight"] == 0


def test_semantic_continuation_runs_even_when_mechanical_budget_is_exhausted(queued):
    db, _, session, queue, job = queued
    with db.connect() as connection:
        connection.execute(
            """UPDATE complete_application_sessions
               SET state='NEEDS_INPUT'
               WHERE session_id=?""",
            (session.session_id,),
        )
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='WAITING_INPUT',attempt_count=3,max_attempts=3
               WHERE job_id=?""",
            (job["job_id"],),
        )
        connection.commit()

    requeued = queue.requeue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-08T03:10:00+00:00",
    )
    assert requeued is not None
    assert requeued["continuation_pending"] == 1

    continuation = queue.claim_next(
        worker_id="worker-continuation",
        now="2026-09-08T03:10:01+00:00",
    )
    assert continuation is not None
    assert continuation["attempt_count"] == 4
    assert continuation["continuation_in_flight"] == 1

    finished = queue.finish(
        job_id=job["job_id"],
        worker_id="worker-continuation",
        session_state="READY_FOR_REVIEW",
        now="2026-09-08T03:10:02+00:00",
    )
    assert finished["attempt_count"] == 3
    assert finished["max_attempts"] == 3
    assert finished["continuation_count"] == 1
    assert finished["state"] == "READY_FOR_REVIEW"


class _FakeService:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def prepare_session(self, *, session_id, adapter):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return SimpleNamespace(state=self.outcome)


def test_worker_maps_ready_for_review_and_never_needs_submit_authority(queued):
    _, _, _, queue, job = queued
    service = _FakeService("READY_FOR_REVIEW")
    worker = DurablePreparationWorker(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=lambda _job: object(),
    )
    result = worker.run_once(
        worker_id="worker-a",
        now="2026-09-08T03:00:00+00:00",
    )
    assert result is not None
    assert result.job_id == job["job_id"]
    assert result.job_state == "READY_FOR_REVIEW"
    assert result.session_state == "READY_FOR_REVIEW"
    assert result.retry_scheduled is False
    assert service.calls == 1


def test_worker_retries_transient_pre_submit_failure_bounded(queued):
    _, _, _, queue, job = queued
    service = _FakeService(TimeoutError("browser process exited"))
    worker = DurablePreparationWorker(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=lambda _job: object(),
    )

    first = worker.run_once(
        worker_id="worker-a",
        now="2026-09-08T03:00:00+00:00",
    )
    assert first is not None
    assert first.job_state == "QUEUED"
    assert first.retry_scheduled is True

    second = worker.run_once(
        worker_id="worker-b",
        now="2026-09-08T03:00:01+00:00",
    )
    assert second is not None
    assert second.job_state == "QUEUED"

    third = worker.run_once(
        worker_id="worker-c",
        now="2026-09-08T03:00:02+00:00",
    )
    assert third is not None
    assert third.job_state == "FAILED_SAFELY"
    assert third.retry_scheduled is False

    stored = queue.get(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
    )
    assert stored["attempt_count"] == 3
    assert stored["lease_owner"] is None


def test_deterministic_preparation_error_fails_without_retry(queued):
    _, _, _, queue, job = queued
    service = _FakeService(ValueError("Hunter plan is stale"))
    worker = DurablePreparationWorker(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=lambda _job: object(),
    )
    result = worker.run_once(
        worker_id="worker-a",
        now="2026-09-08T03:00:00+00:00",
    )
    assert result is not None
    assert result.job_state == "FAILED_SAFELY"
    assert result.retry_scheduled is False

    stored = queue.get(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
    )
    assert stored["attempt_count"] == 1
    assert "Hunter plan is stale" in stored["last_error"]


def test_failed_safely_can_receive_one_explicit_technical_retry(queued):
    _, _, session, queue, job = queued
    claimed = queue.claim_next(
        worker_id="worker-a",
        now="2026-09-08T03:00:00+00:00",
    )
    assert claimed is not None
    failed = queue.fail(
        job_id=job["job_id"],
        worker_id="worker-a",
        error=RuntimeError("provider adapter bug"),
        retryable=False,
        now="2026-09-08T03:00:01+00:00",
    )
    assert failed["state"] == "FAILED_SAFELY"

    retried = queue.retry_failed_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        expected_last_error="provider adapter bug",
        now="2026-09-08T03:00:02+00:00",
    )
    assert retried["state"] == "QUEUED"
    assert retried["attempt_count"] == 1
    assert retried["max_attempts"] == 4
    assert retried["last_error"] is None


def test_waiting_input_without_open_tasks_can_receive_one_bound_retry(queued):
    db, _, session, queue, job = queued
    checkpoint_id = "checkpoint-tech"
    browser_digest = "a" * 64
    with db.connect() as connection:
        connection.execute(
            """UPDATE complete_application_sessions
               SET state='NEEDS_INPUT',checkpoint_id=?,browser_form_digest=?
               WHERE session_id=?""",
            (checkpoint_id, browser_digest, session.session_id),
        )
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='WAITING_INPUT',attempt_count=3,max_attempts=3
               WHERE job_id=?""",
            (job["job_id"],),
        )
        connection.commit()
    retried = queue.retry_waiting_session_without_open_tasks(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        expected_checkpoint_id=checkpoint_id,
        expected_browser_form_digest=browser_digest,
        now="2026-09-08T04:00:00+00:00",
    )
    assert retried["state"]=="QUEUED"
    assert retried["attempt_count"]==3
    assert retried["max_attempts"]==4


def _provider_mechanics_waiting_fixture(queued):
    """One approved, blocked Workday control across two historical checkpoints."""
    import json

    db, _, session, queue, job = queued
    checkpoint_id = "checkpoint-provider-current"
    digest = "b" * 64
    occurred = "2026-10-09T18:51:20+00:00"
    with db.connect() as connection:
        connection.execute(
            """UPDATE complete_application_sessions
               SET state='NEEDS_INPUT',provider='WORKDAY',
                   checkpoint_id=?,browser_form_digest=?
               WHERE session_id=?""",
            (checkpoint_id, digest, session.session_id),
        )
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='WAITING_INPUT',provider='WORKDAY',
                   attempt_count=4,max_attempts=4
               WHERE job_id=?""",
            (job["job_id"],),
        )
        for index, cp in enumerate(("checkpoint-older", checkpoint_id)):
            connection.execute(
                """INSERT INTO resolution_tasks (
                       task_id,schema_version,application_id,session_id,
                       checkpoint_id,page_id,control_id,question_id,question,
                       semantic_type,category,status,risk_level,auto_resolvable,
                       requires_user,grouping_scope,group_key,reason,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"task-provider-{index}", 1, job["application_id"],
                    session.session_id, cp, "page-first", "ctl-referral",
                    "question-referral", "Referral source", "REFERRAL",
                    "MISSING_FACT", "PENDING", "MEDIUM", 1, 0,
                    "EXACT_QUESTION", "group-referral",
                    "Required browser-invalid answer", occurred, occurred,
                ),
            )
        evidence = {
            "field_action_evidence": [{
                "control_id": "ctl-referral",
                "semantic_type": "REFERRAL",
                "status": "FAILED",
                "strategy": "WORKDAY_PROVIDER_PROMPT",
                "plan_match_count": 1,
                "verification": "FAILED_CLOSED",
                "option_diagnostic": "EXACT_OPTION_NOT_VISIBLE",
            }],
        }
        connection.execute(
            """INSERT INTO complete_application_execution_events (
                   event_id,application_id,plan_id,session_id,provider,
                   event_type,replay_identity,evidence_json,occurred_at
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "event-provider-failed", job["application_id"], job["plan_id"],
                session.session_id, "WORKDAY", "FORM_PREPARED",
                "provider-form-prepared", json.dumps(evidence), occurred,
            ),
        )
        connection.commit()
    arguments = dict(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        expected_plan_id=job["plan_id"],
        expected_checkpoint_id=checkpoint_id,
        expected_browser_form_digest=digest,
        expected_control_id="ctl-referral",
        now="2026-10-09T19:00:00+00:00",
    )
    return db, queue, job, arguments


def test_waiting_provider_fix_retry_preserves_signed_plan_and_only_one_attempt(queued):
    db, queue, job, arguments = _provider_mechanics_waiting_fixture(queued)
    result = queue.retry_waiting_session_after_verified_provider_fix(**arguments)
    assert result["state"] == "QUEUED"
    assert result["attempt_count"] == 4
    assert result["max_attempts"] == 5
    assert result["plan_id"] == job["plan_id"]
    assert result["continuation_pending"] == 0
    with pytest.raises(ValueError, match="not eligible"):
        queue.retry_waiting_session_after_verified_provider_fix(**arguments)
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands WHERE application_id=?",
            (job["application_id"],),
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    "corruption",
    ["requires_user", "different_semantic", "no_current_checkpoint", "no_proof"],
)
def test_waiting_provider_fix_rejects_unsafe_input_or_missing_proof(queued, corruption):
    db, queue, job, arguments = _provider_mechanics_waiting_fixture(queued)
    with db.connect() as connection:
        if corruption == "requires_user":
            connection.execute(
                "UPDATE resolution_tasks SET requires_user=1 WHERE session_id=?",
                (arguments["session_id"],),
            )
        elif corruption == "different_semantic":
            connection.execute(
                "UPDATE resolution_tasks SET semantic_type='SELF_ID' WHERE session_id=?",
                (arguments["session_id"],),
            )
        elif corruption == "no_current_checkpoint":
            connection.execute(
                "UPDATE resolution_tasks SET checkpoint_id='wrong' WHERE session_id=?",
                (arguments["session_id"],),
            )
        elif corruption == "no_proof":
            connection.execute(
                "UPDATE complete_application_execution_events SET evidence_json='{}'"
                " WHERE session_id=?",
                (arguments["session_id"],),
            )
        connection.commit()
    with pytest.raises(ValueError):
        queue.retry_waiting_session_after_verified_provider_fix(**arguments)
    unchanged = queue.get(
        job_id=job["job_id"], tenant_id="tenant-a", user_id="member-a"
    )
    assert unchanged["state"] == "WAITING_INPUT"
    assert unchanged["max_attempts"] == 4
