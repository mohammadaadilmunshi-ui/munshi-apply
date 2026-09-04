from __future__ import annotations

import json
import hashlib
import hmac
from pathlib import Path

from munshi_apply_native.career_os_handoff import CareerOSHandoffConsumer
from munshi_apply_native.database import Database


def _consumer(tmp_path: Path) -> tuple[CareerOSHandoffConsumer, Database]:
    database = Database(tmp_path / "apply.sqlite", Path(__file__).resolve().parents[3] / "migrations")
    database.migrate()
    return CareerOSHandoffConsumer(database, bridge_secret="test-bridge-secret"), database


def _package(**changes: object) -> dict[str, object]:
    package: dict[str, object] = {
        "schema_version": "1.0", "tenant_id": "tenant-a", "package_id": "package-1",
        "package_version": 1, "job_id": "job-1", "application_identity": "job:example:1",
        "provider": "greenhouse", "state": "READY_TO_APPLY",
        "idempotency_key": "a" * 24,
        "artifact_references": [{"artifact_id": "resume-1", "sha256": "a" * 64, "kind": "RESUME"}],
        "required_answers": [{"field_id": "salary", "status": "UNRESOLVED"}],
        "evidence_references": ["evidence-1"],
    }
    package.update(changes)
    return package


def _signed(package: dict[str, object], *, timestamp: int = 1000) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(package, separators=(",", ":"), sort_keys=True).encode()
    event_id = "career-os-handoff-1"
    digest = hashlib.sha256(body).hexdigest()
    content = f"{event_id}.{timestamp}.{digest}".encode()
    signature = hmac.new(b"test-bridge-secret", content, hashlib.sha256).hexdigest()
    return body, {
        "X-Munshi-Event-Id": event_id, "X-Munshi-Timestamp": str(timestamp),
        "X-Munshi-Content-SHA256": digest, "X-Munshi-Signature": f"sha256={signature}",
    }


def test_accepts_tenant_bound_package_without_submission(tmp_path: Path) -> None:
    consumer, database = _consumer(tmp_path)
    body, headers = _signed(_package())
    result = consumer.accept(body, headers, now=1000)
    assert result.accepted and result.state == "HANDOFF_ACCEPTED" and not result.replayed
    with database.connect() as connection:
        row = connection.execute("SELECT tenant_id, handoff_state FROM career_os_preparation_handoffs").fetchone()
        assert tuple(row) == ("tenant-a", "READY_TO_APPLY")
        assert connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0


def test_replay_is_idempotent_and_payload_conflicts_fail_closed(tmp_path: Path) -> None:
    consumer, _ = _consumer(tmp_path)
    body, headers = _signed(_package())
    assert consumer.accept(body, headers, now=1000).accepted
    replay = consumer.accept(body, headers, now=1000)
    assert replay.accepted and replay.replayed
    body2, headers2 = _signed(_package(job_id="job-2"))
    conflict = consumer.accept(body2, headers2, now=1000)
    assert not conflict.accepted and conflict.error == "idempotency key payload conflict"


def test_wrong_signature_malformed_and_stale_payloads_are_rejected(tmp_path: Path) -> None:
    consumer, _ = _consumer(tmp_path)
    body, headers = _signed(_package())
    headers["X-Munshi-Signature"] = "sha256=not-a-signature"
    assert consumer.accept(body, headers, now=1000).error == "invalid signature"
    malformed, malformed_headers = _signed({"tenant_id": "tenant-a"})
    assert consumer.accept(malformed, malformed_headers, now=1000).error == "malformed package"
    good_body, good_headers = _signed(_package(), timestamp=1)
    assert consumer.accept(good_body, good_headers, now=1000).error == "invalid signature"


def test_unsupported_provider_is_stored_as_needs_input_without_action(tmp_path: Path) -> None:
    consumer, database = _consumer(tmp_path)
    body, headers = _signed(_package(provider="unknown-ats"))
    result = consumer.accept(body, headers, now=1000)
    assert result.accepted and not result.provider_supported and result.state == "HANDOFF_ACCEPTED"
    with database.connect() as connection:
        assert connection.execute("SELECT handoff_state FROM career_os_preparation_handoffs").fetchone()[0] == "NEEDS_INPUT"


def test_accepts_exact_hunter_phase_9_envelope_over_fresh_signed_bridge(tmp_path: Path) -> None:
    consumer, database = _consumer(tmp_path)
    hunter_envelope = {
        "version": "munshi-apply-preparation-handoff-v1", "handoff_id": "handoff-hunter-1",
        "tenant_id": "tenant-a", "user_id": "member-a", "preparation_id": "prep-1",
        "application_id": "application-1", "job": {"id": 41, "title": "HR Analyst"},
        "provider": "GREENHOUSE", "state": "READY_TO_APPLY", "artifact_references": None,
        "answers": [{"status": "UNRESOLVED"}], "provenance": {"preparation_version": 1},
    }
    body, headers = _signed(hunter_envelope)
    result = consumer.accept(body, headers, now=1000)
    assert result.accepted and result.state == "HANDOFF_ACCEPTED"
    with database.connect() as connection:
        row = connection.execute(
            "SELECT tenant_id, user_id, preparation_id, job_id, handoff_state "
            "FROM career_os_preparation_handoffs"
        ).fetchone()
        assert tuple(row) == ("tenant-a", "member-a", "prep-1", "41", "READY_TO_APPLY")
