from __future__ import annotations

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
        assert health.json()["schema_version"] == "012_resolution_tasks.sql"
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
