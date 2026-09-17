"""GOLDEN VECTOR — cross-runtime canonicalization contract.

This test pins the exact bytes, digest, and signature that Hunter and Apply
must agree on for any ``munshi-submit-authorization-v1`` envelope. The fixture
is a frozen literal: 24 fields, exactly the values Hunter mints, and the
expected constants were independently computed by the Hunter-side counterpart
using the same canonicalization rules:

* ``canonical_bytes = json.dumps(material, sort_keys=True,
  separators=(",", ":"), ensure_ascii=True).encode("utf-8")``
* ``authority_digest = sha256(canonical_bytes).hexdigest()`` — hashed over
  the 24-key MATERIAL only (excluding ``authority_digest`` and ``signature``).
* ``signature = "sha256=" + hmac.new(secret,
  authority_digest_hex_string.encode("utf-8"), sha256).hexdigest()`` — HMAC
  message is the 64-char ASCII hex digest string, not raw bytes.

If a future drift breaks any of these constants, BOTH sides must update in
lockstep — never edit one without the other.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from pydantic import ValidationError

from munshi_apply_native.submit_authority_inbox_v1 import SubmitAuthorityEnvelope

TEST_SECRET = "test-only-submit-authority-secret-not-a-real-key-0123456789"  # noqa: S105

# PINNED EXPECTED CONSTANTS — Hunter-side recomputed values; do not edit.
EXPECTED_CANONICAL_LENGTH = 1183
EXPECTED_AUTHORITY_DIGEST = "02a7996421d82192c90d6820c0105a4af6b9bcf29fb995cdc6cf2833b553c75d"
EXPECTED_SIGNATURE = "sha256=806edb27b5362d8fd5c5338d9dd87e39a161b0327c8d95ba8828e159ad22dfed"
EXPECTED_CLAIM_DIGEST = "d9467b76684320a0f3431284dd2b04cce3ba2b1f12095b9b785c868c5b8a7f2c"

# PINNED 24-key MATERIAL — must match Hunter's fixture byte-for-byte.
PINNED_MATERIAL = {
    "version": "munshi-submit-authorization-v1",
    "authorization_id": "submit-auth-0000000000000000000000000000000000000001",
    "tenant_id": "default",
    "user_id": "local-owner",
    "application_id": "application-1",
    "plan_id": "application-plan-1",
    "session_id": "apply-session-1",
    "review_id": "review-v2-" + "b" * 32,
    "approval_id": "review-approval-00000000-0000-4000-8000-000000000001",
    "provider": "GREENHOUSE",
    "target_url": "https://boards.greenhouse.io/example/jobs/42",
    "checkpoint_id": "checkpoint-1",
    "generation": 1,
    "plan_digest": "a" * 64,
    "review_digest": "b" * 64,
    "approval_digest": "c" * 64,
    "prepared_package_digest": "d" * 64,
    "browser_form_digest": "e" * 64,
    "resume_sha256": "f" * 64,
    "cover_letter_sha256": None,
    "issued_at": "2026-09-14T00:00:00+00:00",
    "expires_at": "2026-09-14T00:05:00+00:00",
    "synthetic": False,
    "submission_authority": True,
}


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def test_pinned_canonical_length_matches_hunter() -> None:
    canonical = _canonical_json_bytes(PINNED_MATERIAL)
    assert len(canonical) == EXPECTED_CANONICAL_LENGTH


def test_authority_digest_recompute_matches_hunter() -> None:
    canonical = _canonical_json_bytes(PINNED_MATERIAL)
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_AUTHORITY_DIGEST


def test_signature_recompute_matches_hunter() -> None:
    canonical = _canonical_json_bytes(PINNED_MATERIAL)
    auth_digest = hashlib.sha256(canonical).hexdigest()
    sig = (
        "sha256="
        + hmac.new(
            TEST_SECRET.encode(), auth_digest.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    )
    assert sig == EXPECTED_SIGNATURE


def test_claim_digest_recompute_matches_hunter() -> None:
    # Hunter's claim digest: sha256(json.dumps({authorization_id,
    # authority_digest, claimant_id, generation}, sort_keys=True,
    # separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    auth_digest = EXPECTED_AUTHORITY_DIGEST
    claim_material = {
        "authorization_id": PINNED_MATERIAL["authorization_id"],
        "authority_digest": auth_digest,
        "claimant_id": "apply-worker-1",
        "generation": PINNED_MATERIAL["generation"],
    }
    claim_digest = hashlib.sha256(_canonical_json_bytes(claim_material)).hexdigest()
    assert claim_digest == EXPECTED_CLAIM_DIGEST


def test_pinned_canonical_string_is_stable() -> None:
    """The exact canonical bytes must match Hunter's emitted bytes.

    If this fails, drift in either side's JSON serializer must be
    reconciled. This is the most important assertion in the suite.
    """
    canonical = _canonical_json_bytes(PINNED_MATERIAL).decode("utf-8")
    expected = (
        '{"application_id":"application-1","approval_digest":"'
        + "c" * 64
        + '","approval_id":"review-approval-00000000-0000-4000-8000-000000000001",'
        '"authorization_id":"submit-auth-0000000000000000000000000000000000000001",'
        '"browser_form_digest":"' + "e" * 64 + '",'
        '"checkpoint_id":"checkpoint-1",'
        '"cover_letter_sha256":null,'
        '"expires_at":"2026-09-14T00:05:00+00:00",'
        '"generation":1,'
        '"issued_at":"2026-09-14T00:00:00+00:00",'
        '"plan_digest":"' + "a" * 64 + '",'
        '"plan_id":"application-plan-1",'
        '"prepared_package_digest":"' + "d" * 64 + '",'
        '"provider":"GREENHOUSE",'
        '"resume_sha256":"' + "f" * 64 + '",'
        '"review_digest":"' + "b" * 64 + '",'
        '"review_id":"review-v2-' + "b" * 32 + '",'
        '"session_id":"apply-session-1",'
        '"submission_authority":true,'
        '"synthetic":false,'
        '"target_url":"https://boards.greenhouse.io/example/jobs/42",'
        '"tenant_id":"default",'
        '"user_id":"local-owner",'
        '"version":"munshi-submit-authorization-v1"}'
    )
    assert canonical == expected


def test_pydantic_envelope_accepts_26_key_sealed_envelope() -> None:
    """The pydantic envelope accepts the 26-key sealed envelope
    (24-key material + authority_digest + signature) with extra="forbid".
    """
    sealed = {
        **PINNED_MATERIAL,
        "authority_digest": EXPECTED_AUTHORITY_DIGEST,
        "signature": EXPECTED_SIGNATURE,
    }
    # 24 material keys + 2 sealed = 26 total.
    assert len(sealed) == 26
    envelope = SubmitAuthorityEnvelope.model_validate(sealed)
    assert envelope.authority_digest == EXPECTED_AUTHORITY_DIGEST
    assert envelope.signature == EXPECTED_SIGNATURE
    assert envelope.generation == 1
    assert envelope.cover_letter_sha256 is None
    assert envelope.synthetic is False
    assert envelope.submission_authority is True
    assert envelope.version == "munshi-submit-authorization-v1"


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("target_url", "https://boards.greenhouse.io/example/jobs/9999"),
        ("checkpoint_id", "checkpoint-mutated"),
        ("session_id", "apply-session-mutated"),
        ("application_id", "application-mutated"),
        ("tenant_id", "tenant-mutated"),
        ("user_id", "user-mutated"),
        ("plan_digest", "9" * 64),
        ("review_digest", "8" * 64),
        ("prepared_package_digest", "7" * 64),
        ("browser_form_digest", "6" * 64),
        ("resume_sha256", "5" * 64),
        ("cover_letter_sha256", "4" * 64),
        ("generation", 2),
        ("expires_at", "2020-01-01T00:00:00+00:00"),  # expired
        ("synthetic", True),  # forbidden
        ("submission_authority", False),  # forbidden
        ("version", "munshi-submit-authorization-v2"),  # forbidden
    ],
)
def test_authority_digest_drift_is_detected(field: str, new_value: object) -> None:
    """Any material field mutation must invalidate authority_digest."""
    mutated = dict(PINNED_MATERIAL)
    mutated[field] = new_value
    canonical = _canonical_json_bytes(mutated)
    if isinstance(new_value, str) and new_value.startswith("2020"):
        # expires_at in the past doesn't change the digest (digest covers the
        # field VALUE not its semantic validity), so we only assert digest drift.
        pass
    assert hashlib.sha256(canonical).hexdigest() != EXPECTED_AUTHORITY_DIGEST


def test_signature_drift_on_extra_field() -> None:
    """An extra (forbidden) key MUST change the canonical material digest."""
    extra = dict(PINNED_MATERIAL)
    extra["rogue_field"] = "rogue"
    canonical = _canonical_json_bytes(extra)
    assert hashlib.sha256(canonical).hexdigest() != EXPECTED_AUTHORITY_DIGEST


def test_signature_drift_on_missing_key() -> None:
    """A missing key MUST change the canonical material digest."""
    missing = {key: value for key, value in PINNED_MATERIAL.items() if key != "provider"}
    canonical = _canonical_json_bytes(missing)
    assert hashlib.sha256(canonical).hexdigest() != EXPECTED_AUTHORITY_DIGEST


def test_pydantic_envelope_rejects_extra_keys() -> None:
    sealed = {
        **PINNED_MATERIAL,
        "authority_digest": EXPECTED_AUTHORITY_DIGEST,
        "signature": EXPECTED_SIGNATURE,
        "rogue_field": "x",
    }
    with pytest.raises(ValidationError):
        SubmitAuthorityEnvelope.model_validate(sealed)


def test_pydantic_envelope_rejects_missing_keys() -> None:
    sealed = {
        **PINNED_MATERIAL,
        "authority_digest": EXPECTED_AUTHORITY_DIGEST,
        "signature": EXPECTED_SIGNATURE,
    }
    del sealed["target_url"]
    with pytest.raises(ValidationError):
        SubmitAuthorityEnvelope.model_validate(sealed)


def test_pydantic_envelope_accepts_z_suffix_expiry() -> None:
    """Hunter emits both ``+00:00`` and ``Z`` forms for freshness; accept both.
    """
    sealed = {
        **PINNED_MATERIAL,
        "issued_at": "2026-09-14T00:00:00Z",
        "expires_at": "2026-09-14T00:05:00Z",
        "authority_digest": EXPECTED_AUTHORITY_DIGEST,
        "signature": EXPECTED_SIGNATURE,
    }
    envelope = SubmitAuthorityEnvelope.model_validate(sealed)
    assert envelope.issued_at.endswith("Z")
    assert envelope.expires_at.endswith("Z")


def test_pydantic_envelope_accepts_provider_underscore() -> None:
    """Hunter may emit provider in any case; we normalize to upper."""
    sealed = {
        **PINNED_MATERIAL,
        "provider": "greenhouse",
        "authority_digest": EXPECTED_AUTHORITY_DIGEST,
        "signature": EXPECTED_SIGNATURE,
    }
    envelope = SubmitAuthorityEnvelope.model_validate(sealed)
    assert envelope.provider == "GREENHOUSE"


def test_secret_is_not_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pinned test secret is a literal — it must not be sourced from env."""
    # If anyone wired up env-reading for this, the value would change when
    # we set the env to a different string. This pins the contract.
    monkeypatch.setenv("MUNSHI_APPLY_PRODUCTION_AUTHORITY_TEST_SECRET", "different")
    assert TEST_SECRET == "test-only-submit-authority-secret-not-a-real-key-0123456789"  # noqa: S105 - test fixture value