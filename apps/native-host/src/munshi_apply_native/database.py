from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


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

    def record_event(self, event: dict[str, Any], *, enqueue_external: bool = True) -> bool:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._event_exists(connection, event["event_id"]):
                return False
            self._write_event(connection, event, enqueue_external=enqueue_external)
        return True

    def record_application_transition(
        self,
        event: dict[str, Any],
        *,
        new_status: str,
        enqueue_external: bool = True,
    ) -> bool:
        """Commit an application status change and its ledger/outbox event atomically."""
        application_id = event.get("application_id")
        if not application_id:
            raise ValueError("Application transition events require application_id")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._event_exists(connection, event["event_id"]):
                return False
            updated = connection.execute(
                """
                UPDATE applications
                SET status = ?, updated_at = ?
                WHERE application_id = ?
                """,
                (new_status, event["occurred_at"], application_id),
            )
            if updated.rowcount != 1:
                raise KeyError(f"Unknown application: {application_id}")
            self._write_event(connection, event, enqueue_external=enqueue_external)
        return True

    @staticmethod
    def _event_exists(connection: sqlite3.Connection, event_id: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM application_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            is not None
        )

    @staticmethod
    def _write_event(
        connection: sqlite3.Connection,
        event: dict[str, Any],
        *,
        enqueue_external: bool,
    ) -> None:
        payload_json = canonical_json(event.get("payload", {}))
        envelope_json = canonical_json(event)
        connection.execute(
            """
            INSERT INTO application_events (
                event_id, application_id, event_type, occurred_at, source, metadata_json,
                schema_version, correlation_id, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event.get("application_id"),
                event["event_type"],
                event["occurred_at"],
                event["source"],
                payload_json,
                event["schema_version"],
                event["correlation_id"],
                hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            ),
        )
        if enqueue_external:
            connection.execute(
                """
                INSERT INTO outbox_events (
                    event_id, schema_version, correlation_id, application_id, event_type,
                    payload_json, created_at, delivery_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    event["event_id"],
                    event["schema_version"],
                    event["correlation_id"],
                    event.get("application_id"),
                    event["event_type"],
                    envelope_json,
                    event["occurred_at"],
                ),
            )

    def append_event(self, event: dict[str, Any]) -> bool:
        """Backward-compatible entry point for native-messaging callers."""
        return self.record_event(event)

    def recover_stale_outbox(self, *, stale_before: str) -> int:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE outbox_events
                SET delivery_status = 'RETRY', next_retry_at = CURRENT_TIMESTAMP,
                    last_error = 'Recovered stale in-flight delivery'
                WHERE delivery_status = 'IN_FLIGHT'
                  AND last_attempt_at < ?
                """,
                (stale_before,),
            )
        return result.rowcount

    def claim_outbox(self, *, now: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT *
                FROM outbox_events
                WHERE delivery_status = 'PENDING'
                   OR (delivery_status = 'RETRY' AND (next_retry_at IS NULL OR next_retry_at <= ?))
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                connection.execute(
                    """
                    UPDATE outbox_events
                    SET delivery_status = 'IN_FLIGHT', attempt_count = attempt_count + 1,
                        last_attempt_at = ?, last_error = NULL
                    WHERE event_id = ?
                    """,
                    (now, row["event_id"]),
                )
                item = dict(row)
                item["delivery_status"] = "IN_FLIGHT"
                item["attempt_count"] += 1
                item["last_attempt_at"] = now
                claimed.append(item)
        return claimed

    def mark_outbox_delivered(self, event_id: str, *, delivered_at: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE outbox_events
                SET delivery_status = 'DELIVERED', delivered_at = ?, next_retry_at = NULL,
                    last_error = NULL
                WHERE event_id = ? AND delivery_status = 'IN_FLIGHT'
                """,
                (delivered_at, event_id),
            )

    def mark_outbox_failed(
        self,
        event_id: str,
        *,
        failed_at: str,
        next_retry_at: str | None,
        error: str,
        max_attempts: int,
    ) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM outbox_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown outbox event: {event_id}")
            status = "DEAD_LETTER" if row["attempt_count"] >= max_attempts else "RETRY"
            connection.execute(
                """
                UPDATE outbox_events
                SET delivery_status = ?, last_attempt_at = ?, next_retry_at = ?,
                    last_error = ?
                WHERE event_id = ?
                """,
                (
                    status,
                    failed_at,
                    None if status == "DEAD_LETTER" else next_retry_at,
                    error[:2000],
                    event_id,
                ),
            )
        return status

    def outbox_counts(self) -> dict[str, int]:
        statuses = ["PENDING", "IN_FLIGHT", "DELIVERED", "RETRY", "DEAD_LETTER"]
        counts = {status: 0 for status in statuses}
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT delivery_status, COUNT(*) AS count
                FROM outbox_events
                GROUP BY delivery_status
                """
            )
            for row in rows:
                counts[row["delivery_status"]] = row["count"]
        return counts

    def health(self) -> dict[str, Any]:
        with self.connect() as connection:
            migration_count = connection.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations"
            ).fetchone()["count"]
            schema_version = connection.execute(
                "SELECT migration FROM schema_migrations ORDER BY migration DESC LIMIT 1"
            ).fetchone()["migration"]
            connection.execute("SELECT 1").fetchone()
        return {
            "status": "healthy",
            "database": "healthy",
            "migration_count": migration_count,
            "schema_version": schema_version,
            "outbox": self.outbox_counts(),
        }
