"""Deterministic production receipt identity (D6 §6 idempotency fix).

The production receipt client/builder historically used ``uuid4()`` to mint
the ``receipt_id``. A worker re-run that reproduced the exact same verified
facts (browser observation + provider lookup + authority + claim) would
fabricate a NEW logical receipt for identical facts. This test pins the
contract that the receipt_id is deterministic from the verified content —
``production-receipt-<receipt_digest[:32]>`` — matching the existing native
convention ``synthetic-submission-receipt-<digest32>``.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[3] / "integrations" / "applypilot" / "bridge"
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

# Load the bridge module with a fake HMAC secret in env.
os.environ.setdefault("MUNSHI_PRODUCTION_RECEIPT_HMAC_SECRET", "a" * 64)
production_submission_verification = importlib.import_module(
    "production_submission_verification"
)


def _sample() -> dict[str, object]:
    return {
        "synthetic": False,
        "submission_authority": True,
        "tenant_id": "default",
        "user_id": "local-owner",
        "application_id": "application-1",
        "plan_id": "plan-1",
        "plan_digest": "a" * 64,
        "session_id": "session-1",
        "review_id": "review-1",
        "approval_id": "approval-1",
        "provider": "GREENHOUSE",
        "target_url": "https://boards.greenhouse.io/example/jobs/42",
        "authorization_id": "auth-1",
        "authority_digest": "b" * 64,
    }


def _claim() -> dict[str, object]:
    return {
        "status": "CLAIMED",
        "submission_authority": True,
        "authorization_id": "auth-1",
        "authority_digest": "b" * 64,
        "claim_digest": "c" * 64,
    }


def _execution() -> dict[str, object]:
    return {
        "status": "COMPLETED",
        "claimed_submission": True,
        "plan_id": "plan-1",
        "plan_digest": "a" * 64,
        "provider": "GREENHOUSE",
        "provider_application_id": "fixture-app-1",
        "submission_observation": {
            "method": "POST",
            "target": "https://boards.greenhouse.io/example/jobs/42",
            "provider_application_id": "fixture-app-1",
        },
    }


def _proof() -> dict[str, object]:
    return {
        "lookup_confirmed": True,
        "provider_application_id": "fixture-app-1",
        "provider": "GREENHOUSE",
        "target_url": "https://boards.greenhouse.io/example/jobs/42",
        "external_observation_id": "obs-1",
        "observed_status": "submitted",
    }


def test_receipt_id_is_deterministic_across_rebuilds() -> None:
    verified_at = "2026-09-14T00:00:00Z"
    first = production_submission_verification.build_verified_receipt(
        authorization=_sample(),
        claim=_claim(),
        execution=_execution(),
        provider_observation=_proof(),
        verified_at=verified_at,
    )
    second = production_submission_verification.build_verified_receipt(
        authorization=_sample(),
        claim=_claim(),
        execution=_execution(),
        provider_observation=_proof(),
        verified_at=verified_at,
    )
    assert first["receipt_id"] == second["receipt_id"]
    assert first["receipt_digest"] == second["receipt_digest"]


def test_receipt_id_derived_from_receipt_digest() -> None:
    receipt = production_submission_verification.build_verified_receipt(
        authorization=_sample(),
        claim=_claim(),
        execution=_execution(),
        provider_observation=_proof(),
        verified_at="2026-09-14T00:00:00Z",
    )
    assert receipt["receipt_id"] == "production-receipt-" + receipt["receipt_digest"][:32]


def test_verified_at_must_be_explicit_for_determinism() -> None:
    """Without an explicit verified_at, the receipt has a clock noise; but
    the digest is still deterministic across same-call rebuilds. With an
    explicit verified_at, it is fully deterministic.
    """
    explicit = production_submission_verification.build_verified_receipt(
        authorization=_sample(),
        claim=_claim(),
        execution=_execution(),
        provider_observation=_proof(),
        verified_at="2026-09-14T00:00:00Z",
    )
    # Two rebuilds with the same explicit verified_at → same receipt_id.
    explicit2 = production_submission_verification.build_verified_receipt(
        authorization=_sample(),
        claim=_claim(),
        execution=_execution(),
        provider_observation=_proof(),
        verified_at="2026-09-14T00:00:00Z",
    )
    assert explicit["receipt_id"] == explicit2["receipt_id"]


def test_invalid_authority_flags_rejected() -> None:
    bad = dict(_sample())
    bad["synthetic"] = True
    try:
        production_submission_verification.build_verified_receipt(
            authorization=bad,
            claim=_claim(),
            execution=_execution(),
            provider_observation=_proof(),
            verified_at="2026-09-14T00:00:00Z",
        )
    except production_submission_verification.ProductionVerificationError:
        return
    raise AssertionError("synthetic authority should have been rejected")


def test_invalid_claim_status_rejected() -> None:
    bad = dict(_claim())
    bad["status"] = "PENDING"
    try:
        production_submission_verification.build_verified_receipt(
            authorization=_sample(),
            claim=bad,
            execution=_execution(),
            provider_observation=_proof(),
            verified_at="2026-09-14T00:00:00Z",
        )
    except production_submission_verification.ProductionVerificationError:
        return
    raise AssertionError("non-CLAIMED claim should have been rejected")