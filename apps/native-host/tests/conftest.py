"""Shared pytest fixtures for the MUNSHI Apply native-host test suite.

This conftest provides the production (non-synthetic) submit-authority inbox
wiring used by tests that drive ``CompleteApplicationLoopService.submit``.
Tests that exercise the §6 canonical-authority gate must seed a claimed
authority via ``seed_production_authority``; without it the gate fails
closed at runtime as required.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.submit_authority_inbox_v1 import (
    PRODUCTION_AUTHORITY_ENV,
    SubmitAuthorityInbox,
    expected_claim_digest,
)

# Obviously-fake test-only HMAC secret. NEVER read from .env or real secrets.
TEST_AUTHORITY_HMAC_SECRET = "test-only-submit-authority-secret-not-a-real-key-0123456789"  # noqa: S105

# Runtime authority fixtures must stay inside the real freshness window no matter
# when CI runs. The cross-runtime golden-vector test keeps its own pinned literal
# timestamps, so making these helper timestamps relative does not weaken the
# canonicalization contract.
_TEST_NOW = datetime.now(UTC)
TEST_ISSUED_AT = (_TEST_NOW - timedelta(minutes=1)).isoformat()
TEST_EXPIRES_AT = (_TEST_NOW + timedelta(minutes=29)).isoformat()


@dataclass(frozen=True)
class _AuthorityFixture:
    authorization_id: str
    authority_digest: str
    signature: str
    envelope: dict[str, Any]


def _canonical_envelope(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sign_authority(envelope: dict[str, Any], *, secret: str) -> tuple[str, str]:
    """Reproduce Hunter's real attestation exactly.

    authority_digest = sha256(canonical(24-key material without authority_digest/
    signature)); signature = sha256=<HMAC(secret, authority_digest_HEX_STRING)>.
    An earlier revision signed the raw body, which is not what Hunter does and
    would have let a wrong-keyed verifier pass its own fixtures.
    """
    material = {
        key: value for key, value in envelope.items()
        if key not in {"authority_digest", "signature"}
    }
    digest = hashlib.sha256(_canonical_envelope(material)).hexdigest()
    signature = hmac.new(
        secret.encode(), digest.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return digest, f"sha256={signature}"


@pytest.fixture
def production_authority_inbox() -> SubmitAuthorityInbox:
    """Return a SubmitAuthorityInbox wired with a fixed test HMAC secret.

    The returned inbox operates on whatever database is in scope; tests must
    ensure the migrations are applied (the ``test_application_plan_handoff_v2
    ._consumer`` helper does this) and that ``PRODUCTION_AUTHORITY_ENV`` is
    enabled via monkeypatch before invoking ``accept()``.
    """
    # We cannot bind a database here because the fixture order matters; tests
    # that need the inbox typically create it via ``make_production_authority_inbox``
    # against their own database. Returning a fresh placeholder keeps the
    # import surface stable.
    raise RuntimeError("Use make_production_authority_inbox(database) instead")


def make_production_authority_inbox(database: Database) -> SubmitAuthorityInbox:
    return SubmitAuthorityInbox(database)


@pytest.fixture(autouse=False)
def enable_production_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PRODUCTION_AUTHORITY_ENV, "true")


def build_authority_envelope(
    *,
    authorization_id: str,
    application_id: str,
    plan_id: str,
    session_id: str,
    review_id: str,
    approval_id: str,
    plan_digest: str,
    review_digest: str,
    approval_digest: str,
    prepared_package_digest: str,
    browser_form_digest: str,
    resume_sha256: str,
    cover_letter_sha256: str | None = None,
    provider: str = "GREENHOUSE",
    target_url: str = "https://example.test/apply",
    checkpoint_id: str = "checkpoint-1",
    tenant_id: str = "tenant-a",
    user_id: str = "member-a",
    generation: int = 1,
) -> dict[str, Any]:
    """Build a Hunter-issued authority envelope dict (no signature).
    Use ``sign_and_accept_authority`` to sign + accept in one step.
    """
    return {
        "version": "munshi-submit-authorization-v1",
        "authorization_id": authorization_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "application_id": application_id,
        "plan_id": plan_id,
        "session_id": session_id,
        "review_id": review_id,
        "approval_id": approval_id,
        "provider": provider,
        "target_url": target_url,
        "checkpoint_id": checkpoint_id,
        "generation": generation,
        "plan_digest": plan_digest,
        "review_digest": review_digest,
        "approval_digest": approval_digest,
        "prepared_package_digest": prepared_package_digest,
        "browser_form_digest": browser_form_digest,
        "resume_sha256": resume_sha256,
        "cover_letter_sha256": cover_letter_sha256,
        "issued_at": TEST_ISSUED_AT,
        "expires_at": TEST_EXPIRES_AT,
        "synthetic": False,
        "submission_authority": True,
        # Placeholder authority_digest/signature; will be overwritten by sign.
        "authority_digest": "0" * 64,
        "signature": "sha256=" + "0" * 64,
    }


def sign_authority_envelope(
    envelope: dict[str, Any], *, secret: str = TEST_AUTHORITY_HMAC_SECRET
) -> dict[str, Any]:
    """Sign the envelope and return it with ``authority_digest`` + ``signature``.

    Mirrors the Hunter contract: ``authority_digest`` is SHA-256 of the
    canonical 24-key MATERIAL (without ``authority_digest`` / ``signature``).
    ``signature`` is ``sha256=<HMAC(secret, authority_digest_hex_string)>`` —
    the HMAC message is the 64-char ASCII hex digest string, not raw bytes.
    """
    material = {key: value for key, value in envelope.items() if key not in {
        "authority_digest", "signature"
    }}
    auth_digest = hashlib.sha256(_canonical_envelope(material)).hexdigest()
    signature = hmac.new(
        secret.encode(), auth_digest.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    signed = dict(envelope)
    signed["authority_digest"] = auth_digest
    signed["signature"] = f"sha256={signature}"
    return signed


def seed_production_authority(
    *,
    database: Database,
    service: Any,
    envelope: dict[str, Any],
    review_id: str,
) -> dict[str, Any]:
    """Persist + claim a production authority envelope for a service session.

    The inbox must already be bound to ``service`` (via
    ``service.bind_submit_authority_inbox(inbox)``) before calling. This
    helper drives the full accept -> claim_for_execution -> finalize_claim
    sequence so the §6 gate passes for ``service.submit``.

    The claim receipt is derived with ``expected_claim_digest`` exactly as
    Hunter derives it, rather than being invented, so the inbox's own
    claim-receipt verification stays meaningful.
    """
    inbox = make_production_authority_inbox(database)
    service.bind_submit_authority_inbox(inbox)
    accepted = inbox.accept(envelope, now=TEST_ISSUED_AT)
    if not accepted.accepted:
        raise AssertionError(f"Failed to seed authority: {accepted.error}")
    proof = inbox.claim_for_execution(
        authorization_id=envelope["authorization_id"],
        now=datetime.now(UTC).isoformat(),
    )
    if not proof.claimed:
        raise AssertionError(f"Failed to claim authority: {proof.error}")
    final = inbox.finalize_claim(
        authorization_id=envelope["authorization_id"],
        claim_digest=expected_claim_digest(
            authorization_id=envelope["authorization_id"],
            authority_digest=envelope["authority_digest"],
            claimant_id=str(proof.claimant_id),
            generation=int(envelope["generation"]),
        ),
        now=datetime.now(UTC).isoformat(),
    )
    if not final.claimed:
        raise AssertionError(f"Failed to finalize authority: {final.error}")
    return {
        "authority_proof": final,
        "review_id": review_id,
        "session_id": envelope["session_id"],
    }
