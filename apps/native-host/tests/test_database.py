from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    assert database.migrate() == ["001_initial.sql", "002_transactional_outbox.sql"]
    assert database.migrate() == []
    assert database.health()["status"] == "healthy"


def event_record() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": "evt-1",
        "correlation_id": "correlation-1",
        "application_id": None,
        "event_type": "PAGE_DETECTED",
        "occurred_at": datetime.now(UTC).isoformat(),
        "source": "munshi-apply",
        "payload": {"controls": 4},
    }


def test_event_and_outbox_are_written_atomically(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    assert database.record_event(event_record()) is True
    with database.connect() as connection:
        ledger_count = connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
        outbox_count = connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0]
    assert ledger_count == 1
    assert outbox_count == 1


def test_duplicate_event_is_idempotent(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    event = event_record()

    assert database.record_event(event) is True
    assert database.record_event(event) is False

    with database.connect() as connection:
        ledger_count = connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
        outbox_count = connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0]
    assert ledger_count == 1
    assert outbox_count == 1


def test_application_state_event_and_outbox_commit_together(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    occurred_at = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-1', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (occurred_at, occurred_at),
        )
    event = {
        **event_record(),
        "event_id": "evt-transition",
        "application_id": "app-1",
        "event_type": "STATUS_CHANGED",
    }

    assert database.record_application_transition(event, new_status="PREPARED") is True

    with database.connect() as connection:
        status = connection.execute(
            "SELECT status FROM applications WHERE application_id = 'app-1'"
        ).fetchone()[0]
        ledger_count = connection.execute(
            "SELECT COUNT(*) FROM application_events WHERE event_id = 'evt-transition'"
        ).fetchone()[0]
        outbox_count = connection.execute(
            "SELECT COUNT(*) FROM outbox_events WHERE event_id = 'evt-transition'"
        ).fetchone()[0]
    assert status == "PREPARED"
    assert ledger_count == 1
    assert outbox_count == 1


def test_failed_application_transition_rolls_back_all_writes(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    event = {
        **event_record(),
        "event_id": "evt-missing-app",
        "application_id": "missing-app",
        "event_type": "STATUS_CHANGED",
    }

    try:
        database.record_application_transition(event, new_status="PREPARED")
    except KeyError:
        pass
    else:
        raise AssertionError("Unknown application transition was accepted")

    with database.connect() as connection:
        ledger_count = connection.execute(
            "SELECT COUNT(*) FROM application_events WHERE event_id = 'evt-missing-app'"
        ).fetchone()[0]
        outbox_count = connection.execute(
            "SELECT COUNT(*) FROM outbox_events WHERE event_id = 'evt-missing-app'"
        ).fetchone()[0]
    assert ledger_count == 0
    assert outbox_count == 0
