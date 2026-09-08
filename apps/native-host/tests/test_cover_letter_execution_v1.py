from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from munshi_apply_native import artifact_fetch_v2 as fetch
from munshi_apply_native.application_plan_handoff_v2 import ApplicationPlanEnvelope
from munshi_apply_native.artifact_fetch_v2 import HunterExecutionBridgeClient

KEY = "phase1d-apply-cover-secret"
RESUME = b"%PDF-1.4\n% resume\n%%EOF\n"
COVER = b"%PDF-1.4\n% cover\n%%EOF\n"
RS = hashlib.sha256(RESUME).hexdigest()
CS = hashlib.sha256(COVER).hexdigest()


def plan():
    p = {
        "version": "munshi-application-plan-v2",
        "application_id": "application-cover",
        "job": {"id": 41, "job_snapshot_digest": "b" * 64},
        "candidate_truth_binding": {"profile_digest": "c" * 64},
        "resume": {
            "artifact_id": "resume-artifact",
            "artifact_reference": "hunter-native-resume://resume/pdf",
            "artifact_sha256": RS,
            "filename": "resume.pdf",
            "mime_type": "application/pdf",
        },
        "cover_letter": {
            "artifact_id": "cover-artifact",
            "artifact_reference": "hunter-cover-letter://cover-artifact/pdf",
            "artifact_sha256": CS,
            "filename": "cover-letter.pdf",
            "mime_type": "application/pdf",
            "submission_authority": False,
        },
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
            "cover_letter_upload": True,
        },
        "answers": [],
        "provider_policy": {"provider": "GREENHOUSE", "permitted": True},
        "expected_state": "READY_TO_APPLY",
        "executable": True,
        "submission_authority": False,
        "automatic_actions_executed": False,
        "plan_id": "plan-cover",
        "idempotency_key": "key-cover",
    }
    dp = {
        k: v
        for k, v in p.items()
        if k not in {"plan_id", "idempotency_key", "plan_digest", "created_at"}
    }
    p["plan_digest"] = hashlib.sha256(
        json.dumps(dp, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return p


def envelope():
    p = plan()
    return {
        "version": "munshi-application-plan-handoff-v2",
        "handoff_id": "handoff-cover",
        "tenant_id": "tenant-a",
        "user_id": "member-a",
        "application_id": p["application_id"],
        "plan_id": p["plan_id"],
        "plan_digest": p["plan_digest"],
        "provider": "GREENHOUSE",
        "state": "READY_TO_APPLY",
        "content_contract": {
            "application_plan_version": "munshi-application-plan-v2",
            "receiver_min_version": 2,
            "receiver_max_version": 2,
        },
        "plan": p,
        "submission_authority": False,
    }


def responder(request):
    p = json.loads(request.content)
    purpose = p["purpose"]
    body = (
        json.dumps(
            {
                "version": fetch.RESPONSE_VERSION,
                "request_id": p["request_id"],
                "purpose": purpose,
                "plan_id": p["plan_id"],
                "plan_digest": p["plan_digest"],
                "fresh": True,
                "submission_authority": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if purpose == fetch.PURPOSE_PLAN_CURRENT
        else (COVER if purpose == fetch.PURPOSE_COVER_LETTER_BYTES else RESUME)
    )
    d = hashlib.sha256(body).hexdigest()
    sig = hmac.new(
        KEY.encode(),
        f"{p['request_id']}.{purpose}.{d}.{p['plan_digest']}".encode(),
        hashlib.sha256,
    ).hexdigest()
    hs = {
        "X-Munshi-Response-Event-Id": p["request_id"],
        "X-Munshi-Response-Purpose": purpose,
        "X-Munshi-Response-SHA256": d,
        "X-Munshi-Plan-Digest": p["plan_digest"],
        "X-Munshi-Response-Signature": f"sha256={sig}",
    }
    if purpose != fetch.PURPOSE_PLAN_CURRENT:
        hs.update(
            {
                "X-Munshi-Artifact-SHA256": CS
                if purpose == fetch.PURPOSE_COVER_LETTER_BYTES
                else RS,
                "X-Munshi-Submission-Authority": "false",
            }
        )
    return httpx.Response(200, content=body, headers=hs)


def test_handoff_exact_optional_cover():
    v = ApplicationPlanEnvelope.model_validate(envelope())
    assert v.plan["cover_letter"]["artifact_sha256"] == CS
    broken = envelope()
    broken["plan"]["cover_letter"]["artifact_sha256"] = "short"
    with pytest.raises(ValueError):
        ApplicationPlanEnvelope.model_validate(broken)


def test_signed_client_fetches_both(monkeypatch):
    monkeypatch.setattr(fetch.time, "time", lambda: 1000)
    c = HunterExecutionBridgeClient(
        base_url="https://hunter.internal",
        secret=KEY,
        tenant_id="tenant-a",
        user_id="member-a",
        transport=httpx.MockTransport(responder),
    )
    p = plan()
    assert c.plan_is_current(p) is True
    assert c.artifact_bytes(p) == RESUME
    assert c.cover_letter_bytes(p) == COVER
    c.close()
