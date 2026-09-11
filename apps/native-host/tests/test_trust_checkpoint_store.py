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
    job = DurablePreparationQueue(db).enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-10T20:00:00+00:00",
    )
    return db, session, job, TrustCheckpointStore(db)


def test_trust_checkpoint_persists_only_safe_location_metadata(trust_context):
    db, _, job, store = trust_context
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
    db, _, job, store = trust_context
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


def test_block_session_for_auth_preserves_fail_closed_database_state(trust_context):
    db, session, job, store = trust_context
    checkpoint = store.observe(
        job_id=job["job_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        checkpoint_kind="AUTHENTICATION",
        current_url="https://auth.example.test/login?return=private",
        page_fingerprint="login-page",
        observed_at="2026-09-10T20:00:01+00:00",
    )
    store.block_session_for_user_auth(
        trust_checkpoint_id=checkpoint["trust_checkpoint_id"],
        tenant_id="tenant-a",
        user_id="member-a",
        now="2026-09-10T20:00:02+00:00",
    )
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
    assert stored["state"] == "BLOCKED"
    assert int(stored["state_version"]) >= 2
    assert application is not None and application["status"] == "BLOCKED"

    decorated = store.decorate_preparation_job(
        job,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    assert decorated["state"] == "QUEUED"
    assert decorated["effective_state"] == WAITING_FOR_USER_AUTH


def test_unknown_checkpoint_kind_is_rejected(trust_context):
    _, _, job, store = trust_context
    with pytest.raises(ValueError, match="Unsupported"):
        store.observe(
            job_id=job["job_id"],
            tenant_id="tenant-a",
            user_id="member-a",
            checkpoint_kind="MAGIC_BYPASS",
            current_url="https://auth.example.test/login",
            page_fingerprint="login-page",
        )
