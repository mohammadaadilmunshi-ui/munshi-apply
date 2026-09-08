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


def test_needs_input_can_requeue_after_resolution(queued):
    _, _, session, queue, job = queued
    assert queue.claim_next(
        worker_id="worker-a",
        now="2026-09-08T03:00:00+00:00",
    )
    waiting = queue.finish(
        job_id=job["job_id"],
        worker_id="worker-a",
        session_state="NEEDS_INPUT",
        now="2026-09-08T03:00:01+00:00",
    )
    assert waiting["state"] == "WAITING_INPUT"

    requeued = queue.requeue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-08T03:00:02+00:00",
    )
    assert requeued is not None
    assert requeued["state"] == "QUEUED"


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
