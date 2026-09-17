from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.architecture_store import ArchitectureStore
from munshi_apply_native.database import Database


def create_store(tmp_path: Path) -> tuple[Database, ArchitectureStore]:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return database, ArchitectureStore(database)


def insert_profile(database: Database, profile_id: str = "profile-1") -> None:
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO profiles (
                profile_id, display_name, schema_version, created_at, updated_at
            ) VALUES (?, 'Profile', 1, ?, ?)
            """,
            (profile_id, now, now),
        )


def insert_resume(
    database: Database,
    resume_id: str,
    sha256: str,
    *,
    version: int = 1,
) -> None:
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO resumes (
                resume_id, family, version, sha256, filename, source_path,
                role_family, active, created_at
            ) VALUES (?, 'master', ?, ?, ?, ?, NULL, 1, ?)
            """,
            (resume_id, version, sha256, f"{resume_id}.pdf", f"/{resume_id}.pdf", now),
        )


def insert_application(database: Database, application_id: str = "app-1") -> None:
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES (?, NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (application_id, now, now),
        )


def test_profile_record_replace_round_trip(tmp_path: Path) -> None:
    database, store = create_store(tmp_path)
    insert_profile(database)
    now = datetime.now(UTC).isoformat()

    record = {
        "record_id": "employment-1",
        "profile_id": "profile-1",
        "kind": "EMPLOYMENT",
        "label": "Employer A",
        "created_at": now,
        "updated_at": now,
        "facts": [
            {
                "fact_id": "record-fact-1",
                "key": "employer_name",
                "value": "Employer A",
                "category": "EMPLOYMENT",
                "trust_level": "USER_CONFIRMED",
                "source": "profile-record",
                "confirmed_at": now,
                "updated_at": now,
                "protected": False,
            }
        ],
    }
    store.save_profile_record(record)

    first = store.profile_records("profile-1", kind="EMPLOYMENT")
    assert len(first) == 1
    assert first[0]["label"] == "Employer A"
    assert first[0]["facts"][0]["value"] == "Employer A"
    assert first[0]["facts"][0]["protected"] is False

    record["label"] = "Employer B"
    record["facts"] = [
        {
            "fact_id": "record-fact-2",
            "key": "job_title",
            "value": "Recruiter",
            "category": "EMPLOYMENT",
            "trust_level": "USER_CONFIRMED",
            "source": "profile-record",
            "confirmed_at": now,
            "updated_at": now,
            "protected": False,
        }
    ]
    store.save_profile_record(record)

    replaced = store.profile_records("profile-1", kind="EMPLOYMENT")
    assert len(replaced) == 1
    assert replaced[0]["label"] == "Employer B"
    assert [fact["key"] for fact in replaced[0]["facts"]] == ["job_title"]
    assert replaced[0]["facts"][0]["value"] == "Recruiter"


def test_resume_selection_is_idempotent_and_immutable(tmp_path: Path) -> None:
    database, store = create_store(tmp_path)
    insert_resume(database, "resume-1", "a" * 64)
    insert_resume(database, "resume-2", "b" * 64, version=2)
    insert_application(database)
    now = datetime.now(UTC).isoformat()
    selection = {
        "selection_id": "selection-1",
        "application_id": "app-1",
        "resume_id": "resume-1",
        "resume_sha256": "a" * 64,
        "locked_at": now,
    }

    assert store.lock_resume_selection(selection) is True
    assert store.lock_resume_selection(selection) is False
    assert store.locked_resume_selection("app-1") == selection

    with pytest.raises(ValueError, match="already locked"):
        store.lock_resume_selection(
            {
                **selection,
                "selection_id": "selection-2",
                "resume_id": "resume-2",
                "resume_sha256": "b" * 64,
            }
        )

    assert store.locked_resume_selection("app-1") == selection


def test_checkpoint_round_trip_returns_latest_sequence(tmp_path: Path) -> None:
    database, store = create_store(tmp_path)
    insert_application(database)
    now = datetime.now(UTC).isoformat()

    store.save_checkpoint(
        {
            "checkpoint_id": "cp-1",
            "application_id": "app-1",
            "sequence": 1,
            "state": "PERSONAL",
            "page_id": "page-1",
            "page_fingerprint": "fingerprint-1",
            "completed_control_ids": ["a"],
            "pending_control_ids": ["b"],
            "selected_resume_id": None,
            "selected_resume_sha256": None,
            "created_at": now,
        }
    )
    store.save_checkpoint(
        {
            "checkpoint_id": "cp-2",
            "application_id": "app-1",
            "sequence": 2,
            "state": "EDUCATION",
            "page_id": "page-2",
            "page_fingerprint": "fingerprint-2",
            "completed_control_ids": ["a", "b"],
            "pending_control_ids": ["c"],
            "selected_resume_id": None,
            "selected_resume_sha256": None,
            "created_at": now,
        }
    )

    checkpoint = store.latest_checkpoint("app-1")
    assert checkpoint is not None
    assert checkpoint["checkpoint_id"] == "cp-2"
    assert checkpoint["sequence"] == 2
    assert checkpoint["completed_control_ids"] == ["a", "b"]
    assert checkpoint["pending_control_ids"] == ["c"]


def test_evidence_graph_round_trip_and_idempotent_edges(tmp_path: Path) -> None:
    database, store = create_store(tmp_path)
    insert_application(database)
    now = datetime.now(UTC).isoformat()

    for evidence_id, text in (
        ("e-1", "Verified profile fact"),
        ("e-2", "Resume evidence"),
    ):
        store.upsert_evidence_node(
            {
                "evidence_id": evidence_id,
                "application_id": "app-1",
                "kind": "PROFILE_FACT" if evidence_id == "e-1" else "RESUME_BULLET",
                "text": text,
                "semantic_types": ["RELEVANT_EXPERIENCE"],
                "trust_level": "VERIFIED",
                "protected": False,
                "source": "test",
                "updated_at": now,
            }
        )

    edge = {
        "from_evidence_id": "e-1",
        "to_evidence_id": "e-2",
        "relation": "SUPPORTS",
    }
    assert store.add_evidence_edge(edge) is True
    assert store.add_evidence_edge(edge) is False

    graph = store.evidence_graph("app-1")
    assert [node["evidence_id"] for node in graph["nodes"]] == ["e-1", "e-2"]
    assert graph["nodes"][0]["semantic_types"] == ["RELEVANT_EXPERIENCE"]
    assert graph["edges"] == [edge]


def test_ai_usage_ledger_sums_only_requested_month(tmp_path: Path) -> None:
    _, store = create_store(tmp_path)
    store.record_ai_usage(
        {
            "usage_id": "usage-1",
            "provider": "openai",
            "model": "gpt-test",
            "occurred_at": "2026-08-14T18:00:00+00:00",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": 1.25,
            "correlation_id": "correlation-1",
        }
    )
    store.record_ai_usage(
        {
            "usage_id": "usage-2",
            "provider": "openai",
            "model": "gpt-test",
            "occurred_at": "2026-07-31T18:00:00+00:00",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": 9.0,
        }
    )

    assert store.monthly_ai_spend("2026-08") == 1.25
    assert store.monthly_ai_spend("2026-07") == 9.0
