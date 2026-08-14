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
        database_path=tmp_path / "api.sqlite",
        migrations_path=migrations,
        n8n_webhook_url=None,
        n8n_webhook_secret=None,
        log_level="INFO",
    )

    with TestClient(main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        accepted = client.post(
            "/v1/events",
            json={
                "eventId": "evt-api-1",
                "eventType": "PAGE_DETECTED",
                "occurredAt": "2026-08-14T12:00:00Z",
                "source": "EXTENSION",
                "applicationId": None,
                "payload": {"controls": 8},
                "schemaVersion": 1,
            },
        )
        assert accepted.status_code == 202
        assert accepted.json() == {"accepted": True}

    with main.database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
    assert count == 1
