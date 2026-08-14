from __future__ import annotations

from .database import Database


class ApplicationStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure(self, application_id: str, observed_at: str) -> bool:
        """Create the durable application identity once without overwriting later state."""
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT application_id FROM applications WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            if existing is not None:
                return False
            connection.execute(
                """
                INSERT INTO applications (
                    application_id, job_id, status, resume_id, job_signal_score,
                    submitted_at, created_at, updated_at
                ) VALUES (?, NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
                """,
                (application_id, observed_at, observed_at),
            )
        return True
