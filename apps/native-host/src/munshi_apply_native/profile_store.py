from __future__ import annotations

import json
from typing import Any

from .database import Database, canonical_json


class ProfileStore:
    """Authoritative desktop profile snapshot stored atomically in SQLite."""

    record_kinds = {"EDUCATION", "EMPLOYMENT", "PROJECT", "CERTIFICATION", "LANGUAGE"}

    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, profile: dict[str, Any]) -> None:
        snapshot = self._validated_snapshot(profile)
        records = snapshot["records"]
        tombstones = snapshot["recordTombstones"]
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
                    snapshot["profileId"],
                    snapshot["displayName"],
                    snapshot["schemaVersion"],
                    snapshot["createdAt"],
                    snapshot["updatedAt"],
                ),
            )
            connection.execute(
                "DELETE FROM facts WHERE profile_id = ?",
                (snapshot["profileId"],),
            )
            for fact in snapshot["facts"]:
                self._insert_fact(connection, snapshot["profileId"], fact)

            connection.execute(
                "DELETE FROM profile_records WHERE profile_id = ?",
                (snapshot["profileId"],),
            )
            for record in records:
                connection.execute(
                    """
                    INSERT INTO profile_records (
                        record_id, profile_id, kind, label, sort_order, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["recordId"],
                        snapshot["profileId"],
                        record["kind"],
                        record["label"],
                        record["sortOrder"],
                        record["createdAt"],
                        record["updatedAt"],
                    ),
                )
                for fact in record["facts"]:
                    self._insert_record_fact(connection, record["recordId"], fact)

            connection.execute(
                "DELETE FROM profile_record_tombstones WHERE profile_id = ?",
                (snapshot["profileId"],),
            )
            for tombstone in tombstones:
                connection.execute(
                    """
                    INSERT INTO profile_record_tombstones (
                        record_id, profile_id, kind, deleted_at, confirmed
                    ) VALUES (?, ?, ?, ?, 1)
                    """,
                    (
                        tombstone["recordId"],
                        snapshot["profileId"],
                        tombstone["kind"],
                        tombstone["deletedAt"],
                    ),
                )

    def _validated_snapshot(self, profile: dict[str, Any]) -> dict[str, Any]:
        required = (
            "profileId",
            "displayName",
            "facts",
            "createdAt",
            "updatedAt",
            "schemaVersion",
        )
        if any(key not in profile for key in required):
            raise ValueError("Profile snapshot is missing required fields")
        if profile["schemaVersion"] != 1 or profile.get("snapshotVersion", 1) != 1:
            raise ValueError("Unsupported profile snapshot version")
        if not isinstance(profile["facts"], list):
            raise ValueError("Profile facts must be an array")
        records = profile.get("records", [])
        tombstones = profile.get("recordTombstones", [])
        if not isinstance(records, list):
            raise ValueError("Profile records must be an array")
        if not isinstance(tombstones, list):
            raise ValueError("Profile record tombstones must be an array")

        record_ids: set[str] = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError("Profile record must be an object")
            record_id = record.get("recordId")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError("Profile record id is required")
            if record_id in record_ids:
                raise ValueError(f"Duplicate profile record id: {record_id}")
            record_ids.add(record_id)
            if record.get("kind") not in self.record_kinds:
                raise ValueError("Profile record kind is invalid")
            if not isinstance(record.get("facts", []), list):
                raise ValueError("Profile record facts must be an array")
            sort_order = record.get("sortOrder", index)
            if not isinstance(sort_order, int) or isinstance(sort_order, bool) or sort_order < 0:
                raise ValueError("Profile record sort order must be a non-negative integer")
            record["sortOrder"] = sort_order

        tombstone_ids: set[str] = set()
        for tombstone in tombstones:
            if not isinstance(tombstone, dict):
                raise ValueError("Profile record tombstone must be an object")
            record_id = tombstone.get("recordId")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError("Profile record tombstone id is required")
            if record_id in tombstone_ids:
                raise ValueError(f"Duplicate profile record tombstone id: {record_id}")
            if record_id in record_ids:
                raise ValueError(f"Record and tombstone overlap: {record_id}")
            tombstone_ids.add(record_id)
            if tombstone.get("kind") not in self.record_kinds:
                raise ValueError("Profile record tombstone kind is invalid")
            if tombstone.get("confirmed") is not True:
                raise ValueError("Profile record deletion must be explicitly confirmed")

        return {
            **profile,
            "records": records,
            "recordTombstones": tombstones,
            "snapshotVersion": 1,
        }

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
                ORDER BY kind, sort_order, record_id
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
                        "sortOrder": record["sort_order"],
                        "createdAt": record["created_at"],
                        "updatedAt": record["updated_at"],
                    }
                )
            tombstones = connection.execute(
                """
                SELECT * FROM profile_record_tombstones
                WHERE profile_id = ?
                ORDER BY deleted_at, record_id
                """,
                (profile["profile_id"],),
            ).fetchall()

        return {
            "profileId": profile["profile_id"],
            "displayName": profile["display_name"],
            "facts": [self._fact_from_row(row) for row in facts],
            "records": result_records,
            "recordTombstones": [
                {
                    "recordId": row["record_id"],
                    "kind": row["kind"],
                    "deletedAt": row["deleted_at"],
                    "confirmed": bool(row["confirmed"]),
                }
                for row in tombstones
            ],
            "createdAt": profile["created_at"],
            "updatedAt": profile["updated_at"],
            "schemaVersion": profile["schema_version"],
            "snapshotVersion": 1,
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
