from __future__ import annotations

from typing import Any

from .database import Database

_MEMORY_STATES = {"ACTIVE", "SUPPRESSED", "ROLLED_BACK"}
_MEMORY_TRANSITIONS = {
    "ACTIVE": {"ACTIVE", "SUPPRESSED", "ROLLED_BACK"},
    "SUPPRESSED": {"ACTIVE", "SUPPRESSED", "ROLLED_BACK"},
    "ROLLED_BACK": {"ROLLED_BACK"},
}
_IDENTITY_FIELDS = (
    "memory_kind",
    "semantic_type",
    "site_origin",
    "component_fingerprint",
    "question_fingerprint",
    "interpretation_key",
    "strategy_key",
    "canonical_option_key",
    "created_at",
)


class ProgressiveMemoryStore:
    """Durable mechanics/interpretation memory without reusable raw answer text."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def save_memory(self, memory: dict[str, Any]) -> bool:
        self._validate(memory)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM progressive_memories WHERE memory_id = ?",
                (memory["memory_id"],),
            ).fetchone()
            if existing is None:
                if memory["version"] != 1:
                    raise ValueError("New memory must start at version 1")
                connection.execute(
                    """
                    INSERT INTO progressive_memories (
                        memory_id, memory_kind, semantic_type, site_origin,
                        component_fingerprint, question_fingerprint,
                        interpretation_key, strategy_key, canonical_option_key,
                        confidence, verified_successes, verified_failures,
                        owner_corrections, created_at, last_observed_at,
                        expires_at, version, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._values(memory),
                )
                return True

            self._validate_update(existing, memory)
            if memory["version"] == existing["version"]:
                return False
            connection.execute(
                """
                UPDATE progressive_memories
                SET confidence = ?, verified_successes = ?, verified_failures = ?,
                    owner_corrections = ?, last_observed_at = ?, expires_at = ?,
                    version = ?, state = ?
                WHERE memory_id = ?
                """,
                (
                    memory["confidence"],
                    memory["verified_successes"],
                    memory["verified_failures"],
                    memory["owner_corrections"],
                    memory["last_observed_at"],
                    memory.get("expires_at"),
                    memory["version"],
                    memory["state"],
                    memory["memory_id"],
                ),
            )
        return True

    def memory(self, memory_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM progressive_memories WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def candidates(
        self,
        *,
        semantic_type: str | None = None,
        site_origin: str | None = None,
        component_fingerprint: str | None = None,
        question_fingerprint: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("Memory candidate limit must be between 1 and 500")
        clauses = ["state = 'ACTIVE'"]
        parameters: list[Any] = []
        if semantic_type is not None:
            clauses.append("(semantic_type IS NULL OR semantic_type = ?)")
            parameters.append(semantic_type)
        if site_origin is not None:
            clauses.append("(site_origin IS NULL OR site_origin = ?)")
            parameters.append(site_origin)
        if component_fingerprint is not None:
            clauses.append(
                "(component_fingerprint IS NULL OR component_fingerprint = ?)"
            )
            parameters.append(component_fingerprint)
        if question_fingerprint is not None:
            clauses.append("(question_fingerprint IS NULL OR question_fingerprint = ?)")
            parameters.append(question_fingerprint)
        parameters.append(limit)
        query = f"""
            SELECT * FROM progressive_memories
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence DESC, last_observed_at DESC, memory_id
            LIMIT ?
        """
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [dict(row) for row in rows]

    def record_observation(self, observation: dict[str, Any]) -> bool:
        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO progressive_memory_observations (
                    observation_id, memory_id, occurred_at, success, verified,
                    owner_corrected, failure_class
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation["observation_id"],
                    observation["memory_id"],
                    observation["occurred_at"],
                    1 if observation.get("success", False) else 0,
                    1 if observation.get("verified", False) else 0,
                    1 if observation.get("owner_corrected", False) else 0,
                    observation.get("failure_class"),
                ),
            )
        return result.rowcount == 1

    def observations(self, memory_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM progressive_memory_observations
                WHERE memory_id = ?
                ORDER BY occurred_at, observation_id
                """,
                (memory_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "success": bool(row["success"]),
                "verified": bool(row["verified"]),
                "owner_corrected": bool(row["owner_corrected"]),
            }
            for row in rows
        ]

    @staticmethod
    def _values(memory: dict[str, Any]) -> tuple[Any, ...]:
        return (
            memory["memory_id"],
            memory["memory_kind"],
            memory.get("semantic_type"),
            memory.get("site_origin"),
            memory.get("component_fingerprint"),
            memory.get("question_fingerprint"),
            memory.get("interpretation_key"),
            memory.get("strategy_key"),
            memory.get("canonical_option_key"),
            memory["confidence"],
            memory["verified_successes"],
            memory["verified_failures"],
            memory["owner_corrections"],
            memory["created_at"],
            memory["last_observed_at"],
            memory.get("expires_at"),
            memory["version"],
            memory["state"],
        )

    @staticmethod
    def _validate(memory: dict[str, Any]) -> None:
        memory_id = memory.get("memory_id")
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError("Memory id is required")
        confidence = memory.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("Memory confidence must be between 0 and 1")
        version = memory.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("Memory version must be a positive integer")
        for field in ("verified_successes", "verified_failures", "owner_corrections"):
            value = memory.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("Memory counters must be non-negative integers")
        if memory.get("state") not in _MEMORY_STATES:
            raise ValueError("Memory state is invalid")
        kind = memory.get("memory_kind")
        if kind == "SITE" and not memory.get("site_origin"):
            raise ValueError("Site memory requires site_origin")
        if kind == "QUESTION" and not memory.get("question_fingerprint"):
            raise ValueError("Question memory requires question_fingerprint")
        if kind == "GLOBAL_PATTERN" and (
            memory.get("site_origin") is not None
            or memory.get("question_fingerprint") is not None
        ):
            raise ValueError("Global pattern memory cannot be site/question bound")
        if kind == "USER_CORRECTION" and not (
            memory.get("question_fingerprint") or memory.get("interpretation_key")
        ):
            raise ValueError("User correction memory requires interpretation context")

    @staticmethod
    def _validate_update(existing: Any, memory: dict[str, Any]) -> None:
        for field in _IDENTITY_FIELDS:
            requested = memory.get(field)
            if existing[field] != requested:
                raise ValueError("Memory id already refers to a different definition")
        if memory["version"] not in {existing["version"], existing["version"] + 1}:
            raise ValueError("Memory updates must advance exactly one version")
        if memory["version"] == existing["version"]:
            mutable_fields = (
                "confidence",
                "verified_successes",
                "verified_failures",
                "owner_corrections",
                "last_observed_at",
                "expires_at",
                "state",
            )
            if any(existing[field] != memory.get(field) for field in mutable_fields):
                raise ValueError("Same-version memory update is not idempotent")
        allowed = _MEMORY_TRANSITIONS.get(existing["state"], set())
        if memory["state"] not in allowed:
            raise ValueError("Invalid memory state transition")
