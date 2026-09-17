from __future__ import annotations

from types import SimpleNamespace

from munshi_apply_native.hosted_prepare_worker import HostedPreparationRunner


class _TwoJobQueue:
    def __init__(self):
        self.jobs = [
            {
                "job_id": "job-fails",
                "session_id": "session-fails",
                "tenant_id": "tenant-a",
                "user_id": "member-a",
                "attempt_count": 1,
            },
            {
                "job_id": "job-succeeds",
                "session_id": "session-succeeds",
                "tenant_id": "tenant-a",
                "user_id": "member-a",
                "attempt_count": 1,
            },
        ]

    def claim_next(self, **_kwargs):
        return self.jobs.pop(0) if self.jobs else None

    def heartbeat(self, **_kwargs):
        return {}

    def get(self, **_kwargs):
        return {"cancel_requested_at": None}

    def fail(self, *, job_id, **_kwargs):
        return {
            "job_id": job_id,
            "session_id": "session-fails",
            "state": "FAILED_SAFELY",
            "attempt_count": 1,
        }

    def finish(self, *, job_id, **_kwargs):
        return {
            "job_id": job_id,
            "session_id": "session-succeeds",
            "state": "READY_FOR_REVIEW",
            "attempt_count": 1,
        }


class _Adapter:
    def close(self):
        return None


class _Service:
    def __init__(self, *, fail=False):
        self.fail = fail

    def preflight_prepare_session(self, _session_id):
        return None

    def prepare_session(self, **_kwargs):
        if self.fail:
            raise ValueError("synthetic unresolved application")
        return SimpleNamespace(state="READY_FOR_REVIEW")


def test_failed_application_does_not_block_next_preparation_job():
    queue = _TwoJobQueue()

    def service_factory(job):
        return _Service(fail=job["job_id"] == "job-fails")

    runner = HostedPreparationRunner(
        queue,
        service_factory=service_factory,
        adapter_factory=lambda _job: _Adapter(),
        lease_seconds=3,
        heartbeat_interval=0.01,
    )

    first = runner.run_once(worker_id="worker-1")
    second = runner.run_once(worker_id="worker-1")

    assert first is not None
    assert first.job_id == "job-fails"
    assert first.job_state == "FAILED_SAFELY"
    assert first.retry_scheduled is False
    assert second is not None
    assert second.job_id == "job-succeeds"
    assert second.job_state == "READY_FOR_REVIEW"
    assert second.session_state == "READY_FOR_REVIEW"
