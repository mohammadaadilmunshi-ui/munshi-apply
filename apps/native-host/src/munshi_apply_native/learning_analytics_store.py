from __future__ import annotations

import json
import re
from typing import Any

from .database import Database, canonical_json

_OPAQUE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_RECIPE_TRANSITIONS = {
    "SHADOW": {"SHADOW", "PROMOTED", "ROLLED_BACK"},
    "PROMOTED": {"PROMOTED", "ROLLED_BACK"},
    "ROLLED_BACK": {"ROLLED_BACK"},
}
_EXPERIMENT_TRANSITIONS = {
    "DRAFT": {"DRAFT", "ACTIVE", "PAUSED", "COMPLETE"},
    "ACTIVE": {"ACTIVE", "PAUSED", "COMPLETE"},
    "PAUSED": {"PAUSED", "ACTIVE", "COMPLETE"},
    "COMPLETE": {"COMPLETE"},
}


class LearningAnalyticsStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_recipe(self, recipe: dict[str, Any]) -> None:
        actions = recipe.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError("Recipe requires at least one action")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM interaction_recipes WHERE recipe_id = ?",
                (recipe["recipe_id"],),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO interaction_recipes (
                        recipe_id, component_fingerprint, semantic_type, site_origin,
                        actions_json, version, state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        recipe["recipe_id"],
                        recipe["component_fingerprint"],
                        recipe.get("semantic_type"),
                        recipe.get("site_origin"),
                        canonical_json({"items": actions}),
                        recipe["version"],
                        recipe["state"],
                        recipe["created_at"],
                        recipe["updated_at"],
                    ),
                )
                return

            existing_actions = json.loads(existing["actions_json"])["items"]
            same_definition = (
                existing["component_fingerprint"] == recipe["component_fingerprint"]
                and existing["semantic_type"] == recipe.get("semantic_type")
                and existing["site_origin"] == recipe.get("site_origin")
                and existing_actions == actions
                and existing["version"] == recipe["version"]
                and existing["created_at"] == recipe["created_at"]
            )
            if not same_definition:
                raise ValueError("Recipe id already refers to a different immutable definition")
            allowed = _RECIPE_TRANSITIONS.get(existing["state"], set())
            if recipe["state"] not in allowed:
                raise ValueError("Invalid recipe state transition")
            connection.execute(
                """
                UPDATE interaction_recipes
                SET state = ?, updated_at = ?
                WHERE recipe_id = ?
                """,
                (recipe["state"], recipe["updated_at"], recipe["recipe_id"]),
            )

    def recipe(self, recipe_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM interaction_recipes WHERE recipe_id = ?",
                (recipe_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["actions"] = json.loads(item.pop("actions_json"))["items"]
        return item

    def record_recipe_attempt(self, attempt: dict[str, Any]) -> bool:
        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO recipe_attempts (
                    attempt_id, recipe_id, application_id, occurred_at,
                    success, verified, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt["attempt_id"],
                    attempt["recipe_id"],
                    attempt.get("application_id"),
                    attempt["occurred_at"],
                    1 if attempt.get("success", False) else 0,
                    1 if attempt.get("verified", False) else 0,
                    attempt.get("failure_reason"),
                ),
            )
        return result.rowcount == 1

    def recipe_attempts(self, recipe_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recipe_attempts
                WHERE recipe_id = ?
                ORDER BY occurred_at, attempt_id
                """,
                (recipe_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "success": bool(row["success"]),
                "verified": bool(row["verified"]),
            }
            for row in rows
        ]

    def record_outcome(self, outcome: dict[str, Any]) -> bool:
        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO application_outcomes (
                    outcome_event_id, application_id, stage, occurred_at, source
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    outcome["outcome_event_id"],
                    outcome["application_id"],
                    outcome["stage"],
                    outcome["occurred_at"],
                    outcome["source"],
                ),
            )
        return result.rowcount == 1

    def application_outcomes(self, application_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM application_outcomes
                WHERE application_id = ?
                ORDER BY occurred_at, outcome_event_id
                """,
                (application_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_attribution_token(self, token: str, application_id: str, created_at: str) -> None:
        if not _OPAQUE_TOKEN.fullmatch(token):
            raise ValueError("Attribution token must be an opaque 8-64 character token")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO attribution_tokens (
                    token, application_id, created_at, revoked_at
                ) VALUES (?, ?, ?, NULL)
                """,
                (token, application_id, created_at),
            )

    def revoke_attribution_token(self, token: str, revoked_at: str) -> bool:
        with self.database.connect() as connection:
            result = connection.execute(
                """
                UPDATE attribution_tokens
                SET revoked_at = ?
                WHERE token = ? AND revoked_at IS NULL
                """,
                (revoked_at, token),
            )
        return result.rowcount == 1

    def save_experiment(self, experiment: dict[str, Any]) -> None:
        variants = experiment.get("variants")
        if not isinstance(variants, list) or len(variants) < 2:
            raise ValueError("Experiment requires at least two variants")
        requested_variants = sorted(
            (
                variant["variant_id"],
                variant["label"],
                float(variant["weight"]),
            )
            for variant in variants
        )
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (experiment["experiment_id"],),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO experiments (
                        experiment_id, label, minimum_sample_per_variant,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        experiment["experiment_id"],
                        experiment["label"],
                        experiment["minimum_sample_per_variant"],
                        experiment["status"],
                        experiment["created_at"],
                        experiment["updated_at"],
                    ),
                )
                for variant in variants:
                    connection.execute(
                        """
                        INSERT INTO experiment_variants (
                            experiment_id, variant_id, label, weight
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            experiment["experiment_id"],
                            variant["variant_id"],
                            variant["label"],
                            variant["weight"],
                        ),
                    )
                return

            existing_variants = sorted(
                (row["variant_id"], row["label"], float(row["weight"]))
                for row in connection.execute(
                    """
                    SELECT variant_id, label, weight
                    FROM experiment_variants
                    WHERE experiment_id = ?
                    """,
                    (experiment["experiment_id"],),
                ).fetchall()
            )
            same_definition = (
                existing["label"] == experiment["label"]
                and existing["minimum_sample_per_variant"]
                == experiment["minimum_sample_per_variant"]
                and existing["created_at"] == experiment["created_at"]
                and existing_variants == requested_variants
            )
            if not same_definition:
                raise ValueError(
                    "Experiment id already refers to a different immutable definition"
                )
            allowed = _EXPERIMENT_TRANSITIONS.get(existing["status"], set())
            if experiment["status"] not in allowed:
                raise ValueError("Invalid experiment status transition")
            connection.execute(
                """
                UPDATE experiments
                SET status = ?, updated_at = ?
                WHERE experiment_id = ?
                """,
                (
                    experiment["status"],
                    experiment["updated_at"],
                    experiment["experiment_id"],
                ),
            )

    def assign_experiment(self, assignment: dict[str, Any]) -> bool:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM experiment_assignments
                WHERE experiment_id = ? AND subject_id = ?
                """,
                (assignment["experiment_id"], assignment["subject_id"]),
            ).fetchone()
            if existing is not None:
                if existing["variant_id"] != assignment["variant_id"]:
                    raise ValueError(
                        "Experiment subject is already assigned to a different variant"
                    )
                return False
            connection.execute(
                """
                INSERT INTO experiment_assignments (
                    experiment_id, subject_id, variant_id, assigned_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    assignment["experiment_id"],
                    assignment["subject_id"],
                    assignment["variant_id"],
                    assignment["assigned_at"],
                ),
            )
        return True

    def experiment_assignments(self, experiment_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM experiment_assignments
                WHERE experiment_id = ?
                ORDER BY subject_id
                """,
                (experiment_id,),
            ).fetchall()
        return [dict(row) for row in rows]
