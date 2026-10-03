from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from munshi_apply_native import hosted_trust_worker as trust_worker
from munshi_apply_native.hosted_trust_worker import (
    TrustAwareAdapterFactory,
    TrustAwareCompleteApplicationLoopService,
    TrustAwareHostedPlanBrowserAdapter,
    UserAuthRequired,
)


class _TrustStore:
    def __init__(self):
        self.observations = []
        self.waiting = []
        self.cleared = []
        self.active = None

    def observe(self, **kwargs):
        self.observations.append(kwargs)
        self.active = {
            "trust_checkpoint_id": "trust-1",
            "checkpoint_kind": kwargs["checkpoint_kind"],
            "status": "WAITING_FOR_USER_AUTH",
        }
        return dict(self.active)

    def active_for_job(self, **_kwargs):
        return None if self.active is None else dict(self.active)

    def record_waiting_for_user_auth(self, **kwargs):
        self.waiting.append(kwargs)
        return dict(self.active or {})

    def clear_after_live_browser_revalidation(self, **kwargs):
        self.cleared.append(kwargs)
        cleared = dict(self.active or {})
        cleared["status"] = "CLEARED"
        cleared["prepare_job_state"] = "QUEUED"
        self.active = None
        return cleared


class _Queue:
    def __init__(self):
        self.requeued = []

    def requeue_session(self, **kwargs):
        self.requeued.append(kwargs)
        return {"job_id": "prepare-job-1", "state": "QUEUED"}


class _DelegateAdapter:
    def __init__(self, *, initial_checkpoint=None, mid_checkpoint=None):
        self.initial_checkpoint = initial_checkpoint
        self.mid_checkpoint = mid_checkpoint
        self.closed = False
        self.inspections = 0

    def inspect_job(self, *, plan):
        self.inspections += 1
        checkpoint = self.initial_checkpoint
        if self.inspections > 1 and self.mid_checkpoint is not None:
            checkpoint = self.mid_checkpoint
        return {
            "provider": "GREENHOUSE",
            "job_id": str(plan["job"]["id"]),
            "current_url": "https://boards.greenhouse.io/acme/jobs/42?opaque=do-not-store",
            "page_id": "page-1",
            "page_fingerprint": "raw-fingerprint",
            "security_checkpoint": checkpoint,
        }

    def prepare_form(self, **_kwargs):
        if self.mid_checkpoint is not None:
            # Model the real PlanBrowserAdapter, which has already inspected the
            # page during preparation before it raises the security-boundary
            # ValueError. The wrapper's follow-up inspect must therefore observe
            # the next page state where the challenge is visible.
            self.inspections += 1
            raise ValueError("Browser identity or security checkpoint blocks preparation")
        return {"ok": True}

    def close(self):
        self.closed = True


class _DelegateService:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome or SimpleNamespace(state="READY_FOR_REVIEW")
        self.error = error
        self.preflight_calls = 0

    def preflight_prepare_session(self, _session_id):
        self.preflight_calls += 1

    def prepare_session(self, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.outcome


def _job():
    return {
        "job_id": "prepare-job-1",
        "tenant_id": "tenant-a",
        "user_id": "member-a",
        "session_id": "session-1",
    }


def _plan():
    return {"job": {"id": "42"}}


def test_initial_security_checkpoint_becomes_control_signal_before_core_block():
    trust = _TrustStore()
    wrapped = TrustAwareHostedPlanBrowserAdapter(
        _DelegateAdapter(initial_checkpoint="MFA"),
        trust_checkpoints=trust,
        job=_job(),
    )
    try:
        wrapped.inspect_job(plan=_plan())
    except UserAuthRequired as signal:
        assert signal.checkpoint["checkpoint_kind"] == "MFA"
    else:
        raise AssertionError("Expected UserAuthRequired")
    assert len(trust.observations) == 1
    assert trust.observations[0]["checkpoint_kind"] == "MFA"
    assert "opaque=do-not-store" in trust.observations[0]["current_url"]
    # The raw URL exists only in process memory until TrustCheckpointStore hashes
    # the path and drops query/fragment before durable persistence.


def test_mid_form_security_checkpoint_becomes_control_signal():
    trust = _TrustStore()
    wrapped = TrustAwareHostedPlanBrowserAdapter(
        _DelegateAdapter(mid_checkpoint="OTP"),
        trust_checkpoints=trust,
        job=_job(),
    )
    try:
        wrapped.prepare_form(plan=_plan(), checkpoint=None, resolved_values={})
    except UserAuthRequired as signal:
        assert signal.checkpoint["checkpoint_kind"] == "OTP"
    else:
        raise AssertionError("Expected UserAuthRequired")
    assert len(trust.observations) == 1


def test_non_security_prepare_value_error_is_not_reclassified():
    trust = _TrustStore()

    class BrokenAdapter(_DelegateAdapter):
        def prepare_form(self, **_kwargs):
            raise ValueError("Hunter plan is stale")

    wrapped = TrustAwareHostedPlanBrowserAdapter(
        BrokenAdapter(), trust_checkpoints=trust, job=_job()
    )
    try:
        wrapped.prepare_form(plan=_plan(), checkpoint=None, resolved_values={})
    except ValueError as error:
        assert "stale" in str(error)
    else:
        raise AssertionError("Expected original ValueError")
    assert trust.observations == []


def test_service_proxy_maps_user_auth_to_resumable_queue_signal():
    trust = _TrustStore()
    trust.active = {
        "trust_checkpoint_id": "trust-1",
        "checkpoint_kind": "CAPTCHA",
        "status": "WAITING_FOR_USER_AUTH",
    }
    delegate = _DelegateService(error=UserAuthRequired(trust.active))
    proxy = TrustAwareCompleteApplicationLoopService(
        delegate, trust_checkpoints=trust, job=_job()
    )
    result = proxy.prepare_session(session_id="session-1", adapter=object())
    assert result.state == "NEEDS_INPUT"
    assert trust.waiting == [
        {
            "trust_checkpoint_id": "trust-1",
            "tenant_id": "tenant-a",
            "user_id": "member-a",
        }
    ]


def test_normal_delegate_outcome_is_preserved():
    trust = _TrustStore()
    delegate = _DelegateService(outcome=SimpleNamespace(state="READY_FOR_REVIEW"))
    proxy = TrustAwareCompleteApplicationLoopService(
        delegate, trust_checkpoints=trust, job=_job()
    )
    result = proxy.prepare_session(session_id="session-1", adapter=object())
    assert result.state == "READY_FOR_REVIEW"
    assert trust.waiting == []


def test_production_runner_wires_runtime_root_for_pre_submit_recovery(
    monkeypatch,
):
    captured = {}
    queue = object()
    trust_store = object()
    base_factory = object()
    wrapped_factory = object()
    runner = object()
    monkeypatch.setenv(trust_worker.BRIDGE_URL_ENV, "https://hunter.internal")
    monkeypatch.setattr(trust_worker, "DurablePreparationQueue", lambda _db: queue)
    monkeypatch.setattr(trust_worker, "TrustCheckpointStore", lambda _db: trust_store)

    def capture_base_factory(*args, **kwargs):
        captured.update(kwargs)
        return base_factory

    monkeypatch.setattr(trust_worker, "HostedAdapterFactory", capture_base_factory)
    monkeypatch.setattr(
        trust_worker,
        "TrustAwareAdapterFactory",
        lambda base, checkpoints: wrapped_factory,
    )
    monkeypatch.setattr(
        trust_worker,
        "TrustAwareHostedPreparationRunner",
        lambda *args, **kwargs: runner,
    )
    settings = SimpleNamespace(
        handoff_hmac_secret=object(),
        runtime_root=Path("/data/runtime"),
    )

    result = trust_worker.build_runner(object(), settings)

    assert result is runner
    assert captured["runtime_root"] == Path("/data/runtime")



@pytest.mark.parametrize(
    ("checkpoint_kind", "scenario"),
    [
        ("CAPTCHA", "captcha"),
        ("MFA", "sms-mfa"),
        ("OTP", "sms-code"),
        ("AUTHENTICATION", "passkey"),
    ],
)
def test_live_browser_checkpoint_retention_revalidates_and_reuses_same_adapter(
    checkpoint_kind,
    scenario,
):
    trust = _TrustStore()
    delegate = _DelegateAdapter(initial_checkpoint=checkpoint_kind)
    factory = TrustAwareAdapterFactory(lambda _job: delegate, trust)
    wrapped = factory(_job())

    with pytest.raises(UserAuthRequired) as raised:
        wrapped.inspect_job(plan=_plan())
    assert raised.value.checkpoint["checkpoint_kind"] == checkpoint_kind

    trust.record_waiting_for_user_auth(
        trust_checkpoint_id="trust-1",
        tenant_id="tenant-a",
        user_id="member-a",
    )
    wrapped.park_for_user_auth(raised.value.checkpoint)
    wrapped.close()
    assert delegate.closed is False

    # Simulate legitimate user completion in the SAME retained browser context.
    # SMS MFA and passkey are never solved by MUNSHI; this only models the
    # post-user-action observation that the challenge has disappeared.
    delegate.initial_checkpoint = None
    assert factory.resume_ready_checkpoints() == 1
    assert trust.cleared

    resumed = factory(_job())
    assert resumed is wrapped
    resumed.close()
    assert delegate.closed is True
    assert scenario in {"captcha", "sms-mfa", "sms-code", "passkey"}
