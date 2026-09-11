from __future__ import annotations

import json

import pytest
from test_application_plan_handoff_v2 import _consumer, _envelope, _signed

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService
from munshi_apply_native.trust_checkpoint_store import (
    WAITING_FOR_USER_AUTH,
    TrustCheckpointStore,
)


@pytest.fixture
def trust_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")
    consumer, db = _consumer(tmp_path)
    body, headers = _signed(_envelope())
    assert consumer.accept(body, headers, now=1000).accepted

    service = CompleteApplicationLoopService(
        db, tenant_id="tenant-a", user_id="member-a"
    )
    session = service.start_session(plan_id="application-plan-1")
    queue = DurablePreparationQueue(db)
    job = queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-10T20:00:00+00:00",
    )
    return db, session, job, queue, TrustCheckpointStore(db)


def test_trust_checkpoint_persists_only_safe_location_metadata(trust_context):
    db, _, job, _, store = trust_context
    checkpoint = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="OTP",
        current_url=(
            "https://auth.example.test/verify/device"
            "?token=never-store-this&code=654321#challenge"
        ),
        page_fingerprint="page-fingerprint-that-is-hashed",
        observed_at="2026-09-10T20:00:01+00:00",
    )

    wire = store.active_wire_for_job(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
    )
    assert wire is not None
    assert wire["effective_state"] == WAITING_FOR_USER_AUTH
    assert wire["checkpoint_kind"] == "OTP"
    assert wire["origin"] == "https://auth.example.test"
    assert len(wire["path_sha256"]) == 64
    assert len(wire["page_fingerprint_sha256"]) == 64

    serialized = json.dumps(checkpoint, sort_keys=True)
    assert "never-store-this" not in serialized
    assert "654321" not in serialized
    assert "page-fingerprint-that-is-hashed" not in serialized
    with db.connect() as connection:
        event_payloads = [
            str(row["evidence_json"])
            for row in connection.execute(
                """SELECT evidence_json
                   FROM complete_application_trust_checkpoint_events
                   WHERE trust_checkpoint_id=?""",
                (checkpoint["trust_checkpoint_id"],),
            )
        ]
    joined = " ".join(event_payloads)
    assert "never-store-this" not in joined
    assert "654321" not in joined


def test_repeat_observation_is_idempotent_and_changed_challenge_invalidates_old(
    trust_context,
):
    db, _, job, _, store = trust_context
    first = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="MFA",
        current_url="https://auth.example.test/mfa?opaque=one",
        page_fingerprint="same-page",
        observed_at="2026-09-10T20:00:01+00:00",
    )
    same = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="MFA",
        current_url="https://auth.example.test/mfa?opaque=two",
        page_fingerprint="same-page",
        observed_at="2026-09-10T20:00:02+00:00",
    )
    assert same["trust_checkpoint_id"] == first["trust_checkpoint_id"]

    second = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="CAPTCHA",
        current_url="https://auth.example.test/human-check",
        page_fingerprint="different-page",
        observed_at="2026-09-10T20:00:03+00:00",
    )
    assert second["trust_checkpoint_id"] != first["trust_checkpoint_id"]
    with db.connect() as connection:
        old = connection.execute(
            """SELECT status FROM complete_application_trust_checkpoints
               WHERE trust_checkpoint_id=?""",
            (first["trust_checkpoint_id"],),
        ).fetchone()
    assert old is not None and old["status"] == "INVALIDATED"


def test_wait_preserves_authoritative_session_and_application_state(trust_context):
    db, session, job, queue, store = trust_context
    claimed = queue.claim_next(
        worker_id="worker-a",
        now="2026-09-10T20:00:01+00:00",
    )
    assert claimed is not None
    checkpoint = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="AUTHENTICATION",
        current_url="https://auth.example.test/login?return=private",
        page_fingerprint="login-page",
        observed_at="2026-09-10T20:00:02+00:00",
    )
    store.record_waiting_for_user_auth(
        trust_checkpoint_id=checkpoint["trust_checkpoint_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-10T20:00:03+00:00",
    )
    waiting = queue.finish(
        job_id=job["job_id"],
        worker_id="worker-a",
        session_state="NEEDS_INPUT",
        now="2026-09-10T20:00:04+00:00",
    )
    assert waiting["state"] == "WAITING_INPUT"

    with db.connect() as connection:
        stored = connection.execute(
            """SELECT state,state_version FROM complete_application_sessions
               WHERE session_id=?""",
            (session.session_id,),
        ).fetchone()
        application = connection.execute(
            """SELECT status FROM applications WHERE application_id=?""",
            (session.application_id,),
        ).fetchone()
    assert stored is not None
    assert stored["state"] == session.state
    assert int(stored["state_version"]) == session.state_version
    assert application is not None and application["status"] == session.state

    decorated = store.decorate_preparation_job(
        waiting,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    assert decorated["state"] == "WAITING_INPUT"
    assert decorated["effective_state"] == WAITING_FOR_USER_AUTH


def test_verified_clear_requeues_exact_waiting_job_without_auth_secrets(trust_context):
    db, _, job, queue, store = trust_context
    assert queue.claim_next(
        worker_id="worker-a",
        now="2026-09-10T20:00:01+00:00",
    ) is not None
    checkpoint = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="OTP",
        current_url="https://auth.example.test/otp?code=never-store-me",
        page_fingerprint="otp-page",
        observed_at="2026-09-10T20:00:02+00:00",
    )
    store.record_waiting_for_user_auth(
        trust_checkpoint_id=checkpoint["trust_checkpoint_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-10T20:00:03+00:00",
    )
    assert queue.finish(
        job_id=job["job_id"],
        worker_id="worker-a",
        session_state="NEEDS_INPUT",
        now="2026-09-10T20:00:04+00:00",
    )["state"] == "WAITING_INPUT"

    cleared = store.clear_after_verified_user_auth(
        trust_checkpoint_id=checkpoint["trust_checkpoint_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        current_url="https://boards.greenhouse.io/acme/jobs/42?session=do-not-store",
        page_fingerprint="post-auth-page",
        security_checkpoint_absent=True,
        now="2026-09-10T20:00:05+00:00",
    )
    assert cleared["status"] == "CLEARED"
    stored = queue.get(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
    )
    assert stored["state"] == "QUEUED"
    assert store.active_wire_for_job(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
    ) is None

    with db.connect() as connection:
        payload = connection.execute(
            """SELECT evidence_json FROM complete_application_trust_checkpoint_events
               WHERE trust_checkpoint_id=? AND event_type='CLEARED'""",
            (checkpoint["trust_checkpoint_id"],),
        ).fetchone()
    assert payload is not None
    assert "do-not-store" not in str(payload["evidence_json"])


def test_clear_refuses_while_security_checkpoint_is_still_present(trust_context):
    _, _, job, queue, store = trust_context
    assert queue.claim_next(
        worker_id="worker-a",
        now="2026-09-10T20:00:01+00:00",
    ) is not None
    checkpoint = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="MFA",
        current_url="https://auth.example.test/mfa",
        page_fingerprint="mfa-page",
    )
    store.record_waiting_for_user_auth(
        trust_checkpoint_id=checkpoint["trust_checkpoint_id"],
        tenant_id="tenant-a",
        user_id="member-a",
    )
    queue.finish(
        job_id=job["job_id"],
        worker_id="worker-a",
        session_state="NEEDS_INPUT",
    )
    with pytest.raises(ValueError, match="security remains active"):
        store.clear_after_verified_user_auth(
            trust_checkpoint_id=checkpoint["trust_checkpoint_id"],
            tenant_id="tenant-a",
            user_id="member-a",
            current_url="https://auth.example.test/mfa",
            page_fingerprint="mfa-page",
            security_checkpoint_absent=False,
        )


def test_unknown_checkpoint_kind_is_rejected(trust_context):
    _, _, job, _, store = trust_context
    with pytest.raises(ValueError, match="Unsupported"):
        store.observe(
            job_id=job["job_id"],
            tenant_id="tenant-a",
            user_id="member-a",
            checkpoint_kind="MAGIC_BYPASS",
            current_url="https://auth.example.test/login",
            page_fingerprint="login-page",
        )
