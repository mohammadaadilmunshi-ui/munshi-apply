from __future__ import annotations

import json
from typing import Any

from .database import Database


def list_interaction_recipes(database: Database, limit: int = 250) -> list[dict[str, Any]]:
    """Return owner-visible recipe metadata without answer values or secrets."""
    bounded_limit = max(1, min(int(limit), 500))
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                r.recipe_id,
                r.site_origin,
                r.semantic_type,
                r.state,
                r.version,
                r.actions_json,
                r.created_at,
                r.updated_at,
                COALESCE(SUM(CASE WHEN a.verified = 1 THEN 1 ELSE 0 END), 0)
                    AS verified_attempts,
                COALESCE(SUM(CASE WHEN a.verified = 1 AND a.success = 1 THEN 1 ELSE 0 END), 0)
                    AS verified_successes
            FROM interaction_recipes AS r
            LEFT JOIN recipe_attempts AS a ON a.recipe_id = r.recipe_id
            GROUP BY
                r.recipe_id,
                r.site_origin,
                r.semantic_type,
                r.state,
                r.version,
                r.actions_json,
                r.created_at,
                r.updated_at
            ORDER BY r.updated_at DESC, r.recipe_id
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            decoded = json.loads(row["actions_json"])
            actions = decoded.get("items", []) if isinstance(decoded, dict) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            actions = []
        result.append(
            {
                "recipeId": str(row["recipe_id"]),
                "siteOrigin": str(row["site_origin"] or ""),
                "semanticType": str(row["semantic_type"] or "UNKNOWN"),
                "state": str(row["state"]),
                "version": int(row["version"]),
                "verifiedAttempts": int(row["verified_attempts"]),
                "verifiedSuccesses": int(row["verified_successes"]),
                "actionCount": len(actions) if isinstance(actions, list) else 0,
                "createdAt": str(row["created_at"]),
                "updatedAt": str(row["updated_at"]),
            }
        )
    return result
