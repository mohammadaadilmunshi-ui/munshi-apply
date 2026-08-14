from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    assert database.migrate() == ["001_initial.sql"]
    assert database.migrate() == []
    assert database.health()["status"] == "healthy"


def test_event_is_written_to_ledger(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    database.append_event(
        {
            "event_id": "evt-1",
            "application_id": None,
            "event_type": "PAGE_DETECTED",
            "occurred_at": datetime.now(UTC).isoformat(),
            "source": "EXTENSION",
            "payload": {"controls": 4},
        }
    )
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
    assert count == 1
