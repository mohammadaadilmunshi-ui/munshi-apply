from __future__ import annotations

from types import SimpleNamespace

from munshi_apply_native.hosted_trust_worker import (
    TrustAwareCompleteApplicationLoopService,
    TrustAwareHostedPlanBrowserAdapter,
    UserAuthRequired,
)


class _TrustStore:
    def __init__(self):
        self.observations = []
        self.blocked = []
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

    def block_session_for_user_auth(self, **kwargs):
        self.blocked.append(kwargs)
        return dict(self.active or {})


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


def test_initial_security_checkpoint_is_persisted_without_solving_it():
    trust = _TrustStore()
    wrapped = TrustAwareHostedPlanBrowserAdapter(
        _DelegateAdapter(initial_checkpoint="MFA"),
        trust_checkpoints=trust,
        job=_job(),
    )
    observation = wrapped.inspect_job(plan=_plan())
    assert observation["security_checkpoint"] == "MFA"
    assert len(trust.observations) == 1
    assert trust.observations[0]["checkpoint_kind"] == "MFA"
    assert "opaque=do-not-store" in trust.observations[0]["current_url"]
    # The raw URL is handed only to TrustCheckpointStore, whose contract hashes/drops
    # query and fragment before durable persistence.


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


def test_service_proxy_maps_mid_form_user_auth_to_blocked_backing_state():
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
    assert result.state == "BLOCKED"
    assert trust.blocked == [
        {
            "trust_checkpoint_id": "trust-1",
            "tenant_id": "tenant-a",
            "user_id": "member-a",
        }
    ]


def test_service_proxy_recognizes_initial_blocked_security_checkpoint():
    trust = _TrustStore()
    trust.active = {
        "trust_checkpoint_id": "trust-1",
        "checkpoint_kind": "AUTHENTICATION",
        "status": "WAITING_FOR_USER_AUTH",
    }
    delegate = _DelegateService(outcome=SimpleNamespace(state="BLOCKED"))

    class Adapter:
        def active_trust_checkpoint(self):
            return dict(trust.active)

    proxy = TrustAwareCompleteApplicationLoopService(
        delegate, trust_checkpoints=trust, job=_job()
    )
    result = proxy.prepare_session(session_id="session-1", adapter=Adapter())
    assert result.state == "BLOCKED"
    assert len(trust.blocked) == 1
