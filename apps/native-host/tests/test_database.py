from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    assert database.migrate() == [
        "001_initial.sql",
        "002_transactional_outbox.sql",
        "003_profile_evidence_checkpoints.sql",
        "004_learning_analytics.sql",
        "005_profile_snapshot_ordering.sql",
        "006_ai_budget_reservations.sql",
        "007_ai_draft_reviews.sql",
    ]
    assert database.migrate() == []
    health = database.health()
    assert health["status"] == "healthy"
    assert health["migration_count"] == 7
    assert health["schema_version"] == "007_ai_draft_reviews.sql"


def test_architecture_tables_are_created_with_integrity_constraints(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()

    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "profile_records",
            "profile_record_facts",
            "evidence_nodes",
            "evidence_edges",
            "application_checkpoints",
            "application_resume_selections",
            "ai_usage",
            "ai_budget_reservations",
            "ai_drafts",
            "interaction_recipes",
            "recipe_attempts",
            "application_outcomes",
            "attribution_tokens",
            "experiments",
            "experiment_variants",
            "experiment_assignments",
            "profile_record_tombstones",
        }.issubset(tables)

        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO profiles (
                profile_id, display_name, schema_version, created_at, updated_at
            ) VALUES ('profile-1', 'Profile', 1, ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO profile_records (
                record_id, profile_id, kind, label, created_at, updated_at
            ) VALUES ('record-1', 'profile-1', 'EMPLOYMENT', 'Employer', ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO profile_record_facts (
                fact_id, record_id, key, value_json, category, trust_level,
                source, confirmed_at, updated_at, protected
            ) VALUES (
                'record-fact-1', 'record-1', 'employer_name', '"Employer"',
                'EMPLOYMENT', 'USER_CONFIRMED', 'profile-record', ?, ?, 0
            )
            """,
            (now, now),
        )
        assert connection.execute("SELECT COUNT(*) FROM profile_record_facts").fetchone()[0] == 1


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
