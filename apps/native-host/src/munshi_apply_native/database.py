from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path, migrations_path: Path) -> None:
        self.path = path
        self.migrations_path = migrations_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> list[str]:
        applied_now: list[str] = []
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            applied = {
                row["migration"]
                for row in connection.execute("SELECT migration FROM schema_migrations")
            }
            for migration in sorted(self.migrations_path.glob("[0-9][0-9][0-9]_*.sql")):
                if migration.name in applied:
                    continue
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (migration) VALUES (?)", (migration.name,)
                )
                applied_now.append(migration.name)
        return applied_now

    def append_event(self, event: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO application_events (
                    event_id, application_id, event_type, occurred_at, source, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event.get("application_id"),
                    event["event_type"],
                    event["occurred_at"],
                    event["source"],
                    json.dumps(event.get("payload", {}), separators=(",", ":")),
                ),
            )

    def health(self) -> dict[str, Any]:
        with self.connect() as connection:
            migration_count = connection.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations"
            ).fetchone()["count"]
            connection.execute("SELECT 1").fetchone()
        return {
            "status": "healthy",
            "database": "healthy",
            "migration_count": migration_count,
        }
