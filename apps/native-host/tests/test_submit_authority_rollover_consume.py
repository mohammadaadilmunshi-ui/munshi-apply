from __future__ import annotations

from conftest import TEST_ISSUED_AT
from test_submit_authority_inbox import (
    _inbox,
    _make_database,
    _seed_full_flow,
    _sign,
)

from munshi_apply_native.submit_authority_inbox_v1 import expected_claim_digest


def test_consume_uses_newest_claimed_authority_generation(tmp_path, monkeypatch) -> None:
    """A superseded RECEIVED authority must never shadow a newer claimed one."""
    database = _make_database(tmp_path)
    generation_one = _seed_full_flow(database, monkeypatch)
    inbox = _inbox(database)

    first = _sign(generation_one)
    assert inbox.accept(first, now=TEST_ISSUED_AT).accepted is True

    generation_two = dict(generation_one)
    generation_two["authorization_id"] = "auth-test-2"
    generation_two["generation"] = 2
    second = _sign(generation_two)
    accepted = inbox.accept(second, now=TEST_ISSUED_AT)
    assert accepted.accepted is True
    assert accepted.authorization_id == "auth-test-2"

    inflight = inbox.claim_for_execution(
        authorization_id="auth-test-2",
        now=TEST_ISSUED_AT,
    )
    assert inflight.claimed is True
    assert inflight.claimant_id

    claim_digest = expected_claim_digest(
        authorization_id="auth-test-2",
        authority_digest=second["authority_digest"],
        claimant_id=str(inflight.claimant_id),
        generation=2,
    )
    finalized = inbox.finalize_claim(
        authorization_id="auth-test-2",
        claim_digest=claim_digest,
        now=TEST_ISSUED_AT,
    )
    assert finalized.claimed is True

    consumed = inbox.consume_for_execution(
        session_id="session-test-1",
        now=TEST_ISSUED_AT,
    )
    assert consumed.claimed is True
    assert consumed.authorization_id == "auth-test-2"
    assert consumed.generation == 2
