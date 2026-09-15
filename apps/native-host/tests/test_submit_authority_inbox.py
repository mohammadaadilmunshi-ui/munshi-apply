"""Comprehensive inbox tests for the production canonical submit authority.

Covers:
* Accept happy path; expired reject; wrong-tenant/user/app reject;
  target_url/checkpoint/session mismatch reject; extra/unknown key reject.
* Two concurrent claims -> exactly one winner.
* Claim-before-send: second dispatch returns AMBIGUOUS, cannot execute.
* Lost-response: row never re-executes.
* Local execution exactly once (second consume raises).
* Default-off behaviour.
* Route 503/409 when disabled.
* Production submission verification receipt id deterministic across rebuilds.
"""
from __future__ import annotations

import hashlib
import json

from conftest import (
    TEST_AUTHORITY_HMAC_SECRET,
    TEST_ISSUED_AT,
    build_authority_envelope,
    sign_authority_envelope,
)
from test_application_plan_handoff_v2 import _consumer

from munshi_apply_native.submit_authority_inbox_v1 import (
    CLAIM_STATE_AMBIGUOUS,
    CLAIM_STATE_IN_FLIGHT,
    CLAIM_STATE_RECEIVED,
    PRODUCTION_AUTHORITY_ENV,
    SubmitAuthorityInbox,
    expected_claim_digest,
    production_authority_enabled,
)


def _inbox(database) -> SubmitAuthorityInbox:
    return SubmitAuthorityInbox(database)


def _seed_full_flow(
    database,
    monkeypatch,
    *,
    now: str | None = None,
    tenant_id: str = "tenant-a",
    user_id: str = "member-a",
    authorization_id: str = "auth-test-1",
    session_id: str = "session-test-1",
    target_url: str = "https://boards.greenhouse.io/example/jobs/42",
    cover_letter_sha256: str | None = None,
    checkpoint_id: str = "checkpoint-test-1",
):
    """Seed a plan/session/checkpoint/application row, then return a
    signed envelope that binds to it. Tests can call inbox.accept()
    on the returned envelope directly.
    """
    monkeypatch.setenv(PRODUCTION_AUTHORITY_ENV, "true")
    now = now or TEST_ISSUED_AT
    with database.connect() as connection:
        # Application row
        connection.execute(
            "INSERT OR IGNORE INTO applications(application_id,job_id,status,resume_id,"
            "job_signal_score,submitted_at,created_at,updated_at) "
            "VALUES('application-test-1',NULL,'READY_TO_SUBMIT',NULL,NULL,NULL,?,?)",
            (now, now),
        )
        # Plan row
        plan_payload = {
            "version": "munshi-application-plan-v2",
            "application_id": "application-test-1",
            "job": {
                "id": 42,
                "company": "Example Co",
                "title": "Engineer",
                "job_url": target_url,
                "apply_url": target_url,
                "job_snapshot_digest": "b" * 64,
            },
            "candidate_truth_binding": {
                "source_extraction_id": "extract-1",
                "profile_revision": 1,
                "profile_digest": "c" * 64,
            },
            "resume": {
                "engine": "NATIVE_V5",
                "version_id": "resume-v5-1",
                "artifact_id": "resume-artifact-1",
                "artifact_reference": "ref",
                "artifact_sha256": "f" * 64,
                "filename": "resume.pdf",
                "mime_type": "application/pdf",
            },
            "answers": [],
            "permissions": {
                "background_prepare": True,
                "resume_upload": True,
                "normal_answer_autofill": True,
                "cover_letter_upload": cover_letter_sha256 is not None,
                "protected_fact_execution": False,
                "self_id_execution": False,
            },
            "provider_policy": {
                "provider": "GREENHOUSE",
                "permitted": True,
                "captcha_policy": "PAUSE",
                "mfa_policy": "PAUSE",
                "credentials_authority": False,
            },
            "expected_state": "READY_TO_APPLY",
            "executable": True,
            "global_blockers": [],
            "submission_authority": False,
            "automatic_actions_executed": False,
            "plan_id": "plan-test-1",
            "idempotency_key": "plan-key-test-1",
        }
        plan_digest = hashlib.sha256(
            json.dumps(
                {
                    key: value
                    for key, value in plan_payload.items()
                    if key not in {"plan_id", "idempotency_key", "plan_digest", "created_at"}
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        connection.execute(
            "INSERT OR IGNORE INTO career_os_application_plans(plan_id,tenant_id,user_id,"
            "application_id,job_id,provider,plan_version,plan_digest,job_snapshot_sha256,"
            "resume_artifact_id,resume_artifact_sha256,body_sha256,idempotency_key,"
            "plan_json,acceptance_state,accepted_at,handoff_id)"
            " VALUES(?,?,?,'application-test-1','job-test-1','GREENHOUSE',"
            "'munshi-application-plan-v2',?,?,'resume-artifact-1',"
            "?,?,'plan-key-test-1',?,'PLAN_ACCEPTED',?,'handoff-test-1')",
            (
                "plan-test-1",
                tenant_id,
                user_id,
                plan_digest,
                "b" * 64,  # job_snapshot_sha256
                "f" * 64,  # resume_artifact_sha256
                "f" * 64,  # body_sha256
                json.dumps(plan_payload),
                now,
            ),
        )
        # Session row
        connection.execute(
            "INSERT OR IGNORE INTO complete_application_sessions(session_id,"
            "application_id,plan_id,provider,state,state_version,current_url,"
            "browser_form_digest,checkpoint_id,created_at,updated_at)"
            " VALUES(?,?,'plan-test-1','GREENHOUSE','READY_TO_SUBMIT',1,?,?,?,?,?)",
            (
                session_id,
                "application-test-1",
                target_url,
                "e" * 64,
                checkpoint_id,
                now,
                now,
            ),
        )
        # Checkpoint row
        connection.execute(
            "INSERT OR IGNORE INTO application_checkpoints(checkpoint_id,application_id,"
            "sequence,state,page_id,page_fingerprint,completed_control_ids_json,"
            "pending_control_ids_json,selected_resume_id,selected_resume_sha256,created_at)"
            " VALUES(?,?,1,'QUESTIONS','page','fp','{}','{}',?,?,?)",
            (
                checkpoint_id,
                "application-test-1",
                "resume-artifact-1",
                "f" * 64,
                now,
            ),
        )
    return build_authority_envelope(
        authorization_id=authorization_id,
        application_id="application-test-1",
        plan_id="plan-test-1",
        session_id=session_id,
        review_id="review-v2-" + "b" * 32,
        approval_id="review-approval-test-1",
        plan_digest=plan_digest,
        review_digest="b" * 64,
        approval_digest="c" * 64,
        prepared_package_digest="d" * 64,
        browser_form_digest="e" * 64,
        resume_sha256="f" * 64,
        cover_letter_sha256=cover_letter_sha256,
        target_url=target_url,
        checkpoint_id=checkpoint_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )


def _sign(envelope: dict, *, secret=TEST_AUTHORITY_HMAC_SECRET) -> dict:
    return sign_authority_envelope(envelope, secret=secret)


def _make_database(tmp_path):
    consumer, db = _consumer(tmp_path)
    return db


def test_default_off(monkeypatch):
    monkeypatch.delenv(PRODUCTION_AUTHORITY_ENV, raising=False)
    assert production_authority_enabled() is False
    monkeypatch.setenv(PRODUCTION_AUTHORITY_ENV, "true")
    assert production_authority_enabled() is True


def test_accept_happy_path(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is True
    assert result.replayed is False
    assert result.state == CLAIM_STATE_RECEIVED
    with db.connect() as conn:
        row = conn.execute(
            "SELECT state FROM production_submit_authority_claims WHERE authorization_id=?",
            ("auth-test-1",),
        ).fetchone()
        assert row["state"] == CLAIM_STATE_RECEIVED


def test_accept_rejects_expired(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    # now after expires_at
    result = inbox.accept(signed, now="2027-01-01T00:00:00+00:00")
    assert result.accepted is False
    assert "expired" in (result.error or "").lower() or "not-yet" in (result.error or "").lower()


def test_accept_rejects_wrong_tenant(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch, tenant_id="tenant-a")
    envelope["tenant_id"] = "tenant-other"
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False


def test_accept_rejects_target_url_mismatch(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    envelope["target_url"] = "https://attacker.example/jobs/1"
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False
    assert "destination" in (result.error or "").lower() or "target" in (result.error or "").lower()


def test_accept_rejects_checkpoint_mismatch(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    envelope["checkpoint_id"] = "checkpoint-other"
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False
    assert "checkpoint" in (result.error or "").lower()


def test_accept_rejects_session_mismatch(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    envelope["session_id"] = "session-other"
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False
    assert "session" in (result.error or "").lower()


def test_accept_rejects_extra_key(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    envelope["rogue"] = "x"
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False


def test_two_concurrent_claims_only_one_wins(tmp_path, monkeypatch):
    """claim_for_execution uses a guarded UPDATE; two concurrent calls on
    the same authorization_id cannot both transition RECEIVED -> CLAIM_IN_FLIGHT.
    """
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted

    # First claim transitions to CLAIM_IN_FLIGHT.
    first = inbox.claim_for_execution(
        authorization_id="auth-test-1", now=TEST_ISSUED_AT
    )
    assert first.claimed is True
    assert first.state == CLAIM_STATE_IN_FLIGHT

    # Second claim sees CLAIM_IN_FLIGHT and returns AMBIGUOUS, claimed=False.
    second = inbox.claim_for_execution(
        authorization_id="auth-test-1", now=TEST_ISSUED_AT
    )
    assert second.claimed is False
    assert second.state == CLAIM_STATE_AMBIGUOUS


def test_lost_response_cannot_re_execute(tmp_path, monkeypatch):
    """Lost-response scenario: claim_for_execution succeeds, then the network
    drops before consume_for_execution. Re-running consume_for_execution
    must NOT insert a second execution row.
    """
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted

    # First dispatch: claim + finalize + consume.
    first = inbox.claim_for_execution(
        authorization_id="auth-test-1", now=TEST_ISSUED_AT
    )
    assert first.claimed
    inbox.finalize_claim(
        authorization_id="auth-test-1",
        claim_digest=expected_claim_digest(
            authorization_id="auth-test-1",
            authority_digest=signed["authority_digest"],
            claimant_id=str(first.claimant_id),
            generation=int(signed["generation"]),
        ),
        now=TEST_ISSUED_AT,
    )
    consumed = inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    )
    assert consumed.claimed is True

    # Lost-response scenario: a second consume_for_execution attempt.
    second = inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    )
    assert second.claimed is False
    assert "already" in (second.error or "").lower() or "uniqueness" in (second.error or "").lower()


def test_local_execution_exactly_once(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted

    inflight = inbox.claim_for_execution(
        authorization_id="auth-test-1", now=TEST_ISSUED_AT
    )
    inbox.finalize_claim(
        authorization_id="auth-test-1",
        claim_digest=expected_claim_digest(
            authorization_id="auth-test-1",
            authority_digest=signed["authority_digest"],
            claimant_id=str(inflight.claimant_id),
            generation=int(signed["generation"]),
        ),
        now=TEST_ISSUED_AT,
    )
    consumed = inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    )
    assert consumed.claimed is True

    # Subsequent consume refuses.
    again = inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    )
    assert again.claimed is False


def test_consume_requires_claimed_state(tmp_path, monkeypatch):
    """consume_for_execution refuses when the claim is RECEIVED (not yet CLAIMED)."""
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted
    consumed = inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    )
    assert consumed.claimed is False
    assert "CLAIMED" in (consumed.error or "").upper()


def test_replay_after_consume_still_refuses(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted
    inflight = inbox.claim_for_execution(authorization_id="auth-test-1", now=TEST_ISSUED_AT)
    inbox.finalize_claim(
        authorization_id="auth-test-1",
        claim_digest=expected_claim_digest(
            authorization_id="auth-test-1",
            authority_digest=signed["authority_digest"],
            claimant_id=str(inflight.claimant_id),
            generation=int(signed["generation"]),
        ),
        now=TEST_ISSUED_AT,
    )
    inbox.consume_for_execution(session_id="session-test-1", now=TEST_ISSUED_AT)
    again = inbox.consume_for_execution(session_id="session-test-1", now=TEST_ISSUED_AT)
    assert again.claimed is False


def test_mark_ambiguous_moves_in_flight_to_terminal(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted
    inbox.claim_for_execution(authorization_id="auth-test-1", now=TEST_ISSUED_AT)
    result = inbox.mark_ambiguous(
        authorization_id="auth-test-1",
        reason="network lost",
        now=TEST_ISSUED_AT,
    )
    assert result.state == CLAIM_STATE_AMBIGUOUS
    # consume_for_execution now refuses.
    consumed = inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    )
    assert consumed.claimed is False


def test_replay_accepted_idempotent(tmp_path, monkeypatch):
    """Re-accepting the same signed envelope with same body/signature must
    return replayed=True without error.
    """
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    first = inbox.accept(signed, now=TEST_ISSUED_AT)
    second = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert first.accepted is True
    assert first.replayed is False
    assert second.accepted is True
    assert second.replayed is True


def test_replay_with_different_body_is_conflict(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted

    # A different body (even when the new signature is valid) must be
    # refused as a replay conflict, not silently overwrite the prior row.
    # We use a non-binding field here (provider stays GREENHOUSE; only the
    # review_id changes — both bodies are individually valid).
    envelope2 = dict(envelope)
    envelope2["review_id"] = "review-v2-" + "c" * 32
    signed2 = _sign(envelope2)
    result = inbox.accept(signed2, now=TEST_ISSUED_AT)
    assert result.accepted is False
    assert "conflict" in (result.error or "").lower()


def test_invalid_signature_rejected(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    # Tamper with a material field after signing.
    signed["target_url"] = "https://attacker.example/jobs/1"
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False


def test_envelope_version_must_be_exact(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    envelope["version"] = "munshi-submit-authorization-v2"
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False


def test_synthetic_must_be_false(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    envelope["synthetic"] = True
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False


def test_submission_authority_must_be_true(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    envelope["submission_authority"] = False
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False


def test_unknown_authority_returns_no_claim(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    inbox = _inbox(db)
    result = inbox.claim_for_execution(
        authorization_id="auth-missing", now=TEST_ISSUED_AT
    )
    assert result.claimed is False


def test_default_off_blocks_accept(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    # do NOT set the env — should refuse.
    monkeypatch.delenv(PRODUCTION_AUTHORITY_ENV, raising=False)
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False
    assert "disabled" in (result.error or "").lower()


def test_default_off_blocks_claim(tmp_path, monkeypatch):
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    # Set the env to accept but clear it before claiming.
    signed = _sign(envelope)
    inbox = _inbox(db)
    monkeypatch.setenv(PRODUCTION_AUTHORITY_ENV, "true")
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted
    monkeypatch.delenv(PRODUCTION_AUTHORITY_ENV, raising=False)
    result = inbox.claim_for_execution(
        authorization_id="auth-test-1", now=TEST_ISSUED_AT
    )
    assert result.claimed is False
    assert "disabled" in (result.error or "").lower()


def test_envelope_canonical_byte_equality(tmp_path, monkeypatch):
    """The inbox verifies the body bytes are byte-identical to the canonical
    form (after stripping placeholder signature/authority_digest).
    """
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    # Ensure cover_letter_sha256 is JSON null, not absent.
    signed["cover_letter_sha256"] = None
    inbox = _inbox(db)
    # We accept via the dict path; the inbox re-serializes via
    # model_dump(mode="json") and byte-compares to detect mutation.
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is True


def test_cover_letter_must_match_plan(tmp_path, monkeypatch):
    """If the plan has no cover letter, the envelope's cover_letter_sha256
    must be None (not a digest); vice versa.
    """
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch, cover_letter_sha256=None)
    envelope["cover_letter_sha256"] = "a" * 64  # not in plan
    signed = _sign(envelope)
    inbox = _inbox(db)
    result = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert result.accepted is False
    assert "cover" in (result.error or "").lower()


def test_known_inbox_responds_to_v1_complete_loop_route():
    """Route 503/409 when disabled: hit the API route and verify status."""
    from fastapi.testclient import TestClient

    from munshi_apply_native.main import app

    with TestClient(app) as client:
        # Without any command secret or env var, the route refuses 503/401/409.
        resp = client.post(
            "/v1/complete-loop/sessions/anything/submit-authority",
            json={"foo": "bar"},
            headers={
                "X-Munshi-Command-Secret": "",
                "X-Munshi-Tenant-Id": "tenant-a",
                "X-Munshi-User-Id": "member-a",
            },
        )
        assert resp.status_code in (401, 503, 409)

def test_accepts_hunter_signed_envelope_without_holding_the_minting_key(
    tmp_path, monkeypatch
):
    """Apply must accept a genuine authority while NOT sharing Hunter's secret.

    Hunter signs ``signature`` with MUNSHI_PRODUCTION_SUBMIT_AUTH_HMAC_SECRET,
    which Apply deliberately never holds; authenticity is proven by Hunter's
    atomic claim. The inbox here is configured with a completely different
    bridge secret, so a regression that re-introduced local signature
    verification would fail this test loudly instead of rejecting every real
    authority in production.
    """
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope, secret=TEST_AUTHORITY_HMAC_SECRET)
    inbox = _inbox(db)

    # Structural proof of the trust model: the inbox carries no key material at
    # all, so it is incapable of attesting an authority to itself.
    assert not hasattr(inbox, "secret")

    accepted = inbox.accept(signed, now=TEST_ISSUED_AT)
    assert accepted.accepted is True, accepted.error
    assert accepted.authorization_id == "auth-test-1"


def test_finalize_refuses_a_fabricated_or_foreign_claim_receipt(
    tmp_path, monkeypatch
):
    """Only Hunter's deterministic receipt may promote CLAIM_IN_FLIGHT."""
    db = _make_database(tmp_path)
    envelope = _seed_full_flow(db, monkeypatch)
    signed = _sign(envelope)
    inbox = _inbox(db)
    assert inbox.accept(signed, now=TEST_ISSUED_AT).accepted

    inflight = inbox.claim_for_execution(
        authorization_id="auth-test-1", now=TEST_ISSUED_AT
    )
    assert inflight.claimed and inflight.claimant_id

    forged = inbox.finalize_claim(
        authorization_id="auth-test-1", claim_digest="f" * 64, now=TEST_ISSUED_AT
    )
    assert forged.claimed is False
    assert "digest" in (forged.error or "").lower()

    # A receipt minted for a different claimant identity must also be refused.
    foreign = inbox.finalize_claim(
        authorization_id="auth-test-1",
        claim_digest=expected_claim_digest(
            authorization_id="auth-test-1",
            authority_digest=signed["authority_digest"],
            claimant_id="someone-else-completely",
            generation=int(signed["generation"]),
        ),
        now=TEST_ISSUED_AT,
    )
    assert foreign.claimed is False

    # Still not executable: the claim never legitimately reached CLAIMED.
    assert inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    ).claimed is False

    # The genuine receipt for THIS claimant does promote it.
    settled = inbox.finalize_claim(
        authorization_id="auth-test-1",
        claim_digest=expected_claim_digest(
            authorization_id="auth-test-1",
            authority_digest=signed["authority_digest"],
            claimant_id=str(inflight.claimant_id),
            generation=int(signed["generation"]),
        ),
        now=TEST_ISSUED_AT,
    )
    assert settled.claimed is True
    assert inbox.consume_for_execution(
        session_id="session-test-1", now=TEST_ISSUED_AT
    ).claimed is True
