from __future__ import annotations

import time
from types import SimpleNamespace

from munshi_apply_native.background_prepare_queue import PreparationRunResult
from munshi_apply_native.hosted_prepare_worker import HostedPreparationRunner, _target_url


def _plan():
    return {
        "job": {
            "apply_url": "https://boards.greenhouse.io/example/jobs/41",
            "job_url": "https://boards.greenhouse.io/example/jobs/41",
        },
        "provider_policy": {"provider": "GREENHOUSE", "allowed_hosts": ["greenhouse.io"]},
        "submission_authority": False,
    }


def test_target_url_is_provider_and_host_bound():
    assert _target_url(_plan()) == "https://boards.greenhouse.io/example/jobs/41"
    wrong = _plan()
    wrong["job"]["apply_url"] = "https://example.com/jobs/41"
    try:
        _target_url(wrong)
    except ValueError as error:
        assert "provider" in str(error)
    else:
        raise AssertionError("Wrong-provider target was accepted")


class _Queue:
    def __init__(self):
        self.job = {
            "job_id": "job-1",
            "session_id": "session-1",
            "tenant_id": "tenant-a",
            "user_id": "member-a",
            "attempt_count": 1,
        }
        self.heartbeats = 0
        self.finished = None
        self.failed = None

    def claim_next(self, **_kwargs):
        job, self.job = self.job, None
        return job

    def heartbeat(self, **_kwargs):
        self.heartbeats += 1
        return {}

    def finish(self, **kwargs):
        self.finished = kwargs
        return {
            "job_id": "job-1",
            "session_id": "session-1",
            "state": "READY_FOR_REVIEW",
            "attempt_count": 1,
        }

    def fail(self, **kwargs):
        self.failed = kwargs
        return {
            "job_id": "job-1",
            "session_id": "session-1",
            "state": "QUEUED" if kwargs["retryable"] else "FAILED_SAFELY",
            "attempt_count": 1,
        }

    def get(self, **_kwargs):
        return {"cancel_requested_at": None}


class _Adapter:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _Service:
    def __init__(self, state="READY_FOR_REVIEW", error=None):
        self.state = state
        self.error = error

    def prepare_session(self, **_kwargs):
        time.sleep(0.03)
        if self.error:
            raise self.error
        return SimpleNamespace(state=self.state)

    def preflight_prepare_session(self, _session_id):
        return None


def test_runner_heartbeats_finishes_and_closes_adapter():
    queue = _Queue()
    adapter = _Adapter()
    runner = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: _Service(),
        adapter_factory=lambda _job: adapter,
        lease_seconds=3,
        heartbeat_interval=0.01,
    )
    result = runner.run_once(worker_id="worker-1")
    assert isinstance(result, PreparationRunResult)
    assert result.job_state == "READY_FOR_REVIEW"
    assert queue.heartbeats >= 1
    assert queue.finished is not None
    assert queue.failed is None
    assert adapter.closed is True


def test_runner_requeues_transient_browser_failure_and_closes():
    queue = _Queue()
    adapter = _Adapter()
    runner = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: _Service(error=TimeoutError("browser crashed")),
        adapter_factory=lambda _job: adapter,
        lease_seconds=3,
        heartbeat_interval=0.01,
    )
    result = runner.run_once(worker_id="worker-1")
    assert result is not None
    assert result.job_state == "QUEUED"
    assert result.retry_scheduled is True
    assert queue.failed["retryable"] is True
    assert adapter.closed is True


def test_runner_does_not_construct_adapter_when_preflight_fails():
    queue = _Queue()

    class RejectingService(_Service):
        def preflight_prepare_session(self, _session_id):
            raise ValueError("stale session")

    runner = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: RejectingService(),
        adapter_factory=lambda _job: (_ for _ in ()).throw(AssertionError("adapter constructed")),
    )
    result = runner.run_once(worker_id="worker-1")
    assert result is not None and result.job_state == "FAILED_SAFELY"
