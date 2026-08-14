from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.architecture_store import ArchitectureStore
from munshi_apply_native.database import Database


def test_resume_lock_rejects_hash_that_does_not_match_resume_row(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    store = ArchitectureStore(database)
    now = datetime.now(UTC).isoformat()

    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO resumes (
                resume_id, family, version, sha256, filename, source_path,
                role_family, active, created_at
            ) VALUES ('resume-1', 'master', 1, ?, 'resume.pdf', '/resume.pdf', NULL, 1, ?)
            """,
            ("a" * 64, now),
        )
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-1', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (now, now),
        )

    with pytest.raises(ValueError, match="does not match"):
        store.lock_resume_selection(
            {
                "selection_id": "selection-1",
                "application_id": "app-1",
                "resume_id": "resume-1",
                "resume_sha256": "b" * 64,
                "locked_at": now,
            }
        )

    assert store.locked_resume_selection("app-1") is None
