from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from munshi_apply_native import main
from munshi_apply_native.database import Database
from munshi_apply_native.settings import Settings


def test_health_and_event_round_trip(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    main.database = Database(tmp_path / "api.sqlite", migrations)
    main.settings = Settings(
        runtime_root=tmp_path,
        database_path=tmp_path / "api.sqlite",
        migrations_path=migrations,
        n8n_webhook_url=None,
        n8n_webhook_secret=None,
        outbox_poll_seconds=0.01,
        log_level="INFO",
    )

    with TestClient(main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        assert (
            health.json()["schema_version"]
            == "020_durable_user_auth_trust_checkpoints.sql"
        )
        assert health.json()["outbox_worker"] == "disabled"

        accepted = client.post(
            "/v1/events",
            json={
                "schema_version": "1.0",
                "event_id": "evt-api-1",
                "correlation_id": "correlation-api-1",
                "event_type": "PAGE_DETECTED",
                "occurred_at": "2026-08-14T12:00:00Z",
                "source": "munshi-apply",
                "application_id": None,
                "payload": {"controls": 8},
            },
        )
        assert accepted.status_code == 202
        assert accepted.json() == {"accepted": True, "duplicate": False}

        duplicate = client.post(
            "/v1/events",
            json={
                "schema_version": "1.0",
                "event_id": "evt-api-1",
                "correlation_id": "correlation-api-1",
                "event_type": "PAGE_DETECTED",
                "occurred_at": "2026-08-14T12:00:00Z",
                "source": "munshi-apply",
                "application_id": None,
                "payload": {"controls": 8},
            },
        )
        assert duplicate.json() == {"accepted": True, "duplicate": True}

    with main.database.connect() as connection:
        ledger_count = connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
        outbox_count = connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0]
    assert ledger_count == 1
    assert outbox_count == 1


def test_complete_loop_commands_are_default_off_and_require_owner_auth(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    main.database = Database(tmp_path / "api-loop.sqlite", migrations)
    main.settings = Settings(
        runtime_root=tmp_path,
        database_path=tmp_path / "api-loop.sqlite",
        migrations_path=migrations,
        n8n_webhook_url=None,
        n8n_webhook_secret=None,
        outbox_poll_seconds=0.01,
        log_level="INFO",
    )
    with TestClient(main.app) as client:
        disabled = client.post("/v1/complete-loop/sessions", json={"plan_id": "plan-1"})
        assert disabled.status_code == 503

        main.settings = Settings(
            runtime_root=tmp_path,
            database_path=tmp_path / "api-loop.sqlite",
            migrations_path=migrations,
            n8n_webhook_url=None,
            n8n_webhook_secret=None,
            outbox_poll_seconds=0.01,
            log_level="INFO",
            command_secret="fixture-command-secret",  # noqa: S106
        )
        rejected = client.post(
            "/v1/complete-loop/sessions",
            json={"plan_id": "plan-1"},
            headers={"x-munshi-command-secret": "wrong"},
        )
        assert rejected.status_code == 401
        missing_owner = client.post(
            "/v1/complete-loop/sessions",
            json={"plan_id": "plan-1"},
            headers={"x-munshi-command-secret": "fixture-command-secret"},
        )
        assert missing_owner.status_code == 401


def test_application_plan_handoff_http_boundary_is_fail_closed_and_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    main.database = Database(tmp_path / "api-handoff.sqlite", migrations)

    main.settings = Settings(
        runtime_root=tmp_path,
        database_path=tmp_path / "api-handoff.sqlite",
        migrations_path=migrations,
        n8n_webhook_url=None,
        n8n_webhook_secret=None,
        outbox_poll_seconds=0.01,
        log_level="INFO",
    )

    with TestClient(main.app) as client:
        disabled = client.post("/v1/application-plan-handoffs", content=b"{}")
        assert disabled.status_code == 503

        bridge_key = "synthetic-http-handoff-key-123"
        monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
        main.settings = Settings(
            runtime_root=tmp_path,
            database_path=tmp_path / "api-handoff.sqlite",
            migrations_path=migrations,
            n8n_webhook_url=None,
            n8n_webhook_secret=None,
            outbox_poll_seconds=0.01,
            log_level="INFO",
            handoff_hmac_secret=bridge_key,
        )

        plan: dict[str, object] = {
            "version": "munshi-application-plan-v2",
            "application_id": "application-http-1",
            "job": {
                "id": 401,
                "company": "Synthetic Fixture Company",
                "title": "HR Analyst",
                "job_url": "https://boards.greenhouse.io/example/jobs/401",
                "apply_url": "https://boards.greenhouse.io/example/jobs/401",
                "job_snapshot_digest": "b" * 64,
            },
            "candidate_truth_binding": {
                "source_extraction_id": "extract-http-1",
                "profile_revision": 1,
                "profile_digest": "c" * 64,
            },
            "resume": {
                "engine": "NATIVE_V5",
                "version_id": "resume-http-v1",
                "artifact_id": "resume-http-artifact-1",
                "artifact_reference": "hunter-native-resume://resume-http-v1/pdf/digest",
                "artifact_sha256": "d" * 64,
                "filename": "synthetic_resume.pdf",
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
            "plan_id": "application-plan-http-1",
            "idempotency_key": "plan-http-key-1",
        }
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

        envelope = {
            "version": "munshi-application-plan-handoff-v2",
            "handoff_id": "plan-handoff-http-1",
            "tenant_id": "tenant-http",
            "user_id": "member-http",
            "application_id": "application-http-1",
            "plan_id": "application-plan-http-1",
            "plan_digest": plan["plan_digest"],
            "provider": "GREENHOUSE",
            "state": "READY_TO_APPLY",
            "content_contract": {
                "application_plan_version": "munshi-application-plan-v2",
                "receiver_min_version": 2,
                "receiver_max_version": 2,
            },
            "plan": plan,
            "submission_authority": False,
        }
        body = json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        event_id = str(envelope["handoff_id"])
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body).hexdigest()
        signed = f"{event_id}.{timestamp}.{body_hash}".encode()
        signature = hmac.new(
            bridge_key.encode(),
            signed,
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Munshi-Event-Id": event_id,
            "X-Munshi-Timestamp": timestamp,
            "X-Munshi-Content-SHA256": body_hash,
            "X-Munshi-Signature": f"sha256={signature}",
        }

        accepted = client.post(
            "/v1/application-plan-handoffs",
            content=body,
            headers=headers,
        )
        assert accepted.status_code == 202
        assert accepted.json()["accepted"] is True
        assert accepted.json()["replayed"] is False
        assert accepted.json()["state"] == "PLAN_ACCEPTED"
        assert accepted.json()["handoff_id"] == event_id
        assert accepted.json()["plan_id"] == "application-plan-http-1"

        replay = client.post(
            "/v1/application-plan-handoffs",
            content=body,
            headers=headers,
        )
        assert replay.status_code == 202
        assert replay.json()["accepted"] is True
        assert replay.json()["replayed"] is True

    with main.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM career_os_application_plans"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM complete_application_sessions"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM application_submission_receipts"
        ).fetchone()[0] == 0


def test_direct_apply_task_resolution_is_closed_in_favor_of_hunter_supersession(
    tmp_path: Path,
) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    main.database = Database(tmp_path / "api-resolution.sqlite", migrations)
    main.settings = Settings(
        runtime_root=tmp_path,
        database_path=tmp_path / "api-resolution.sqlite",
        migrations_path=migrations,
        n8n_webhook_url=None,
        n8n_webhook_secret=None,
        outbox_poll_seconds=0.01,
        log_level="INFO",
        command_secret="fixture-command-secret",  # noqa: S106
    )
    with TestClient(main.app) as client:
        response = client.post(
            "/v1/complete-loop/tasks/task-1/resolve",
            json={"value": "Aadil", "approved_by_user": True},
            headers={
                "x-munshi-command-secret": "fixture-command-secret",
                "x-munshi-tenant-id": "tenant-a",
                "x-munshi-user-id": "member-a",
            },
        )
    assert response.status_code == 409
    assert "Hunter-authorized replacement Application Plan" in response.json()["detail"]
