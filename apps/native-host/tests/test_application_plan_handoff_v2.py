from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from munshi_apply_native.application_plan_handoff_v2 import ApplicationPlanHandoffConsumer
from munshi_apply_native.database import Database

_SECRET = "synthetic-complete-loop-bridge-secret"


def _consumer(tmp_path: Path) -> tuple[ApplicationPlanHandoffConsumer, Database]:
    database = Database(
        tmp_path / "apply.sqlite",
        Path(__file__).resolve().parents[3] / "migrations",
    )
    database.migrate()
    return ApplicationPlanHandoffConsumer(database, bridge_secret=_SECRET), database


def _plan(**changes: object) -> dict[str, object]:
    plan: dict[str, object] = {
        "version": "munshi-application-plan-v2",
        "application_id": "application-1",
        "job": {
            "id": 41,
            "company": "Fixture Company",
            "title": "HR Analyst",
            "job_url": "https://boards.greenhouse.io/example/jobs/41",
            "apply_url": "https://boards.greenhouse.io/example/jobs/41",
            "job_snapshot_digest": "b" * 64,
        },
        "candidate_truth_binding": {
            "source_extraction_id": "extract-1",
            "profile_revision": 3,
            "profile_digest": "c" * 64,
        },
        "resume": {
            "engine": "NATIVE_V5",
            "version_id": "resume-v5-1",
            "artifact_id": "resume-artifact-1",
            "artifact_reference": "hunter-native-resume://resume-v5-1/pdf/digest",
            "artifact_sha256": "d" * 64,
            "filename": "fixture_resume.pdf",
            "mime_type": "application/pdf",
        },
        "answers": [],
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
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
        "plan_id": "application-plan-1",
        "idempotency_key": "plan-key-1",
    }
    plan.update(changes)
    digest_payload = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "idempotency_key", "plan_digest", "created_at"}
    }
    plan["plan_digest"] = hashlib.sha256(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return plan


def _envelope(
    *,
    plan: dict[str, object] | None = None,
    handoff_id: str = "plan-handoff-1",
    **changes: object,
) -> dict[str, object]:
    actual_plan = plan or _plan()
    envelope: dict[str, object] = {
        "version": "munshi-application-plan-handoff-v2",
        "handoff_id": handoff_id,
        "tenant_id": "tenant-a",
        "user_id": "member-a",
        "application_id": str(actual_plan["application_id"]),
        "plan_id": str(actual_plan["plan_id"]),
        "plan_digest": str(actual_plan["plan_digest"]),
        "provider": "GREENHOUSE",
        "state": "READY_TO_APPLY",
        "content_contract": {
            "application_plan_version": "munshi-application-plan-v2",
            "receiver_min_version": 2,
            "receiver_max_version": 2,
        },
        "plan": actual_plan,
        "submission_authority": False,
    }
    envelope.update(changes)
    return envelope


def _signed(
    envelope: dict[str, object],
    *,
    timestamp: int = 1000,
    event_id: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    replay_id = event_id or str(envelope["handoff_id"])
    digest = hashlib.sha256(body).hexdigest()
    signed_content = f"{replay_id}.{timestamp}.{digest}".encode("utf-8")
    signature = hmac.new(_SECRET.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return body, {
        "X-Munshi-Event-Id": replay_id,
        "X-Munshi-Timestamp": str(timestamp),
        "X-Munshi-Content-SHA256": digest,
        "X-Munshi-Signature": f"sha256={signature}",
    }


def test_live_handoff_is_default_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", raising=False)
    consumer, database = _consumer(tmp_path)
    body, headers = _signed(_envelope())

    result = consumer.accept(body, headers, now=1000)

    assert not result.accepted
    assert result.error == "live handoff disabled"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM career_os_application_plans").fetchone()[0] == 0


def test_accepts_exact_plan_without_browser_or_application_side_effect(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    consumer, database = _consumer(tmp_path)
    body, headers = _signed(_envelope())

    result = consumer.accept(body, headers, now=1000)

    assert result.accepted and not result.replayed and result.state == "PLAN_ACCEPTED"
    with database.connect() as connection:
        stored = connection.execute(
            "SELECT tenant_id,user_id,application_id,acceptance_state FROM career_os_application_plans"
        ).fetchone()
        assert tuple(stored) == ("tenant-a", "member-a", "application-1", "PLAN_ACCEPTED")
        # Acceptance is deliberately inert: it cannot create an execution session,
        # browser event, or authoritative application/submission record.
        assert connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM complete_application_sessions").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM complete_application_execution_events").fetchone()[0]
            == 0
        )
        assert connection.execute("SELECT COUNT(*) FROM final_submit_commands").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM application_submission_receipts").fetchone()[0] == 0


def test_exact_replay_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "1")
    consumer, database = _consumer(tmp_path)
    body, headers = _signed(_envelope())

    first = consumer.accept(body, headers, now=1000)
    replay = consumer.accept(body, headers, now=1000)

    assert first.accepted and not first.replayed
    assert replay.accepted and replay.replayed and replay.state == "PLAN_ACCEPTED"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM career_os_application_plans").fetchone()[0] == 1


def test_tampered_body_and_stale_transport_fail_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    consumer, database = _consumer(tmp_path)
    body, headers = _signed(_envelope())
    tampered = body.replace(b"Fixture Company", b"Other Company")

    assert consumer.accept(tampered, headers, now=1000).error == "invalid signature"
    stale_body, stale_headers = _signed(_envelope(handoff_id="plan-handoff-stale"), timestamp=1)
    assert consumer.accept(stale_body, stale_headers, now=1000).error == "invalid signature"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM career_os_application_plans").fetchone()[0] == 0


def test_event_plan_application_provider_and_version_bindings_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    consumer, database = _consumer(tmp_path)

    body, headers = _signed(_envelope(), event_id="different-event")
    assert consumer.accept(body, headers, now=1000).error == "event identity mismatch"

    wrong_application_plan = _plan(application_id="application-other")
    wrong_application = _envelope(plan=wrong_application_plan, application_id="application-1")
    body, headers = _signed(wrong_application, timestamp=1001)
    assert consumer.accept(body, headers, now=1001).error == "malformed or invalid plan"

    wrong_provider = _envelope(provider="LEVER")
    body, headers = _signed(wrong_provider, timestamp=1002)
    assert consumer.accept(body, headers, now=1002).error == "malformed or invalid plan"

    unsupported_version = _envelope(version="munshi-application-plan-handoff-v99")
    body, headers = _signed(unsupported_version, timestamp=1003)
    assert consumer.accept(body, headers, now=1003).error == "malformed or invalid plan"

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM career_os_application_plans").fetchone()[0] == 0


def test_plan_digest_and_idempotency_conflicts_are_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    consumer, database = _consumer(tmp_path)

    broken_digest = _envelope(plan_digest="f" * 64)
    body, headers = _signed(broken_digest)
    assert consumer.accept(body, headers, now=1000).error == "malformed or invalid plan"

    first_body, first_headers = _signed(_envelope())
    assert consumer.accept(first_body, first_headers, now=1000).accepted

    conflicting_plan = _plan(
        plan_id="application-plan-2",
        idempotency_key="plan-key-1",
        application_id="application-2",
    )
    conflicting = _envelope(
        plan=conflicting_plan,
        handoff_id="plan-handoff-2",
    )
    body, headers = _signed(conflicting, timestamp=1001)
    conflict = consumer.accept(body, headers, now=1001)
    assert not conflict.accepted
    assert conflict.error == "idempotency or replay payload conflict"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM career_os_application_plans").fetchone()[0] == 1
