from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2

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
        "008_progressive_memory.sql",
        "009_account_orchestration.sql",
        "010_job_signal_intelligence.sql",
        "011_job_signal_identity_and_analytics.sql",
        "012_career_os_preparation_handoffs.sql",
    ]
    assert database.migrate() == []
    health = database.health()
    assert health["status"] == "healthy"
    assert health["migration_count"] == 12
    assert health["schema_version"] == "012_career_os_preparation_handoffs.sql"


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
            "progressive_memories",
            "progressive_memory_observations",
            "account_records",
            "account_application_links",
            "job_signal_reports",
            "job_signal_dimensions",
            "job_signal_evidence",
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


def test_job_signal_identity_migration_preserves_existing_reports(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    legacy_migrations = tmp_path / "legacy-migrations"
    legacy_migrations.mkdir()
    for migration in sorted(migrations.glob("0[0-1][0-9]_*.sql")):
        if migration.name >= "011_job_signal_identity_and_analytics.sql":
            continue
        copy2(migration, legacy_migrations / migration.name)

    database_path = tmp_path / "upgrade.sqlite"
    legacy = Database(database_path, legacy_migrations)
    legacy.migrate()
    now = datetime.now(UTC).isoformat()
    with legacy.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('application-legacy', NULL, 'DETECTED', NULL, 42, NULL, ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO job_signal_reports (
                report_id, application_id, overall_signal, overall_score,
                source_fingerprint, evaluated_at, created_at, updated_at
            ) VALUES (
                'report-legacy', 'application-legacy', 'MODERATE', 42,
                'source-legacy', ?, ?, ?
            )
            """,
            (now, now, now),
        )
        connection.execute(
            """
            INSERT INTO job_signal_dimensions (
                report_id, dimension, score, confidence
            ) VALUES ('report-legacy', 'TRAVEL_BURDEN', 70, 0.98)
            """
        )
        connection.execute(
            """
            INSERT INTO job_signal_evidence (
                signal_id, report_id, dimension, severity, evidence, explanation
            ) VALUES (
                'signal-legacy', 'report-legacy', 'TRAVEL_BURDEN', 'HIGH',
                '40% travel', 'The posting explicitly states 40% travel.'
            )
            """
        )

    upgraded = Database(database_path, migrations)
    assert upgraded.migrate() == [
        "011_job_signal_identity_and_analytics.sql",
        "012_career_os_preparation_handoffs.sql",
    ]
    with upgraded.connect() as connection:
        report = connection.execute(
            "SELECT * FROM job_signal_reports WHERE report_id = 'report-legacy'"
        ).fetchone()
        assert report["job_id"] == "job-legacy-application-legacy"
        assert report["source_identity"] == "legacy:source-legacy"
        assert (
            connection.execute(
                "SELECT job_id FROM applications WHERE application_id = 'application-legacy'"
            ).fetchone()[0]
            == "job-legacy-application-legacy"
        )
        evidence = connection.execute(
            "SELECT direction, source FROM job_signal_evidence WHERE signal_id = 'signal-legacy'"
        ).fetchone()
        assert tuple(evidence) == ("CONCERN", "JOB_POSTING")


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
