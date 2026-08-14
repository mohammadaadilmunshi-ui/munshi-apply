from __future__ import annotations

import json
from typing import Any

from .database import Database, canonical_json


class ProfileStore:
    """Authoritative desktop profile snapshot stored atomically in SQLite."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, profile: dict[str, Any]) -> None:
        records = profile.get("records", [])
        if not isinstance(records, list):
            raise ValueError("Profile records must be an array")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO profiles (
                    profile_id, display_name, schema_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    schema_version = excluded.schema_version,
                    updated_at = excluded.updated_at
                """,
                (
                    profile["profileId"],
                    profile["displayName"],
                    profile["schemaVersion"],
                    profile["createdAt"],
                    profile["updatedAt"],
                ),
            )
            connection.execute(
                "DELETE FROM facts WHERE profile_id = ?",
                (profile["profileId"],),
            )
            for fact in profile.get("facts", []):
                self._insert_fact(connection, profile["profileId"], fact)

            connection.execute(
                "DELETE FROM profile_records WHERE profile_id = ?",
                (profile["profileId"],),
            )
            for record in records:
                connection.execute(
                    """
                    INSERT INTO profile_records (
                        record_id, profile_id, kind, label, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["recordId"],
                        profile["profileId"],
                        record["kind"],
                        record["label"],
                        record["createdAt"],
                        record["updatedAt"],
                    ),
                )
                for fact in record.get("facts", []):
                    self._insert_record_fact(connection, record["recordId"], fact)

    @staticmethod
    def _insert_fact(connection: Any, profile_id: str, fact: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO facts (
                fact_id, profile_id, key, value_json, category, trust_level,
                source, confirmed_at, updated_at, protected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact["factId"],
                profile_id,
                fact["key"],
                canonical_json({"value": fact.get("value")}),
                fact["category"],
                fact["trustLevel"],
                fact["source"],
                fact.get("confirmedAt"),
                fact["updatedAt"],
                1 if fact.get("protected", False) else 0,
            ),
        )

    @staticmethod
    def _insert_record_fact(connection: Any, record_id: str, fact: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO profile_record_facts (
                fact_id, record_id, key, value_json, category, trust_level,
                source, confirmed_at, updated_at, protected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact["factId"],
                record_id,
                fact["key"],
                canonical_json({"value": fact.get("value")}),
                fact["category"],
                fact["trustLevel"],
                fact["source"],
                fact.get("confirmedAt"),
                fact["updatedAt"],
                1 if fact.get("protected", False) else 0,
            ),
        )

    def latest(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            profile = connection.execute(
                """
                SELECT * FROM profiles
                ORDER BY updated_at DESC, profile_id
                LIMIT 1
                """
            ).fetchone()
            if profile is None:
                return None
            facts = connection.execute(
                """
                SELECT * FROM facts
                WHERE profile_id = ?
                ORDER BY key, fact_id
                """,
                (profile["profile_id"],),
            ).fetchall()
            records = connection.execute(
                """
                SELECT * FROM profile_records
                WHERE profile_id = ?
                ORDER BY kind, updated_at DESC, record_id
                """,
                (profile["profile_id"],),
            ).fetchall()
            result_records: list[dict[str, Any]] = []
            for record in records:
                record_facts = connection.execute(
                    """
                    SELECT * FROM profile_record_facts
                    WHERE record_id = ?
                    ORDER BY key, fact_id
                    """,
                    (record["record_id"],),
                ).fetchall()
                result_records.append(
                    {
                        "recordId": record["record_id"],
                        "kind": record["kind"],
                        "label": record["label"],
                        "facts": [self._fact_from_row(row) for row in record_facts],
                        "createdAt": record["created_at"],
                        "updatedAt": record["updated_at"],
                    }
                )

        return {
            "profileId": profile["profile_id"],
            "displayName": profile["display_name"],
            "facts": [self._fact_from_row(row) for row in facts],
            "records": result_records,
            "createdAt": profile["created_at"],
            "updatedAt": profile["updated_at"],
            "schemaVersion": profile["schema_version"],
        }

    @staticmethod
    def _fact_from_row(row: Any) -> dict[str, Any]:
        return {
            "factId": row["fact_id"],
            "key": row["key"],
            "value": json.loads(row["value_json"])["value"],
            "category": row["category"],
            "trustLevel": row["trust_level"],
            "source": row["source"],
            "confirmedAt": row["confirmed_at"],
            "updatedAt": row["updated_at"],
            "protected": bool(row["protected"]),
        }
