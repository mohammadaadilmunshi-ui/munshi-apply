from __future__ import annotations

import sys

from .ai_settings import AISettingsStore
from .database import Database
from .native_messaging import handle as legacy_handle
from .native_messaging import read_message, write_message
from .settings import Settings


def list_interaction_recipes(database: Database) -> list[dict[str, object]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                r.recipe_id,
                r.component_fingerprint,
                r.semantic_type,
                r.site_origin,
                r.state,
                r.version,
                r.created_at,
                r.updated_at,
                SUM(CASE WHEN a.verified = 1 THEN 1 ELSE 0 END) AS verified_attempts,
                SUM(CASE WHEN a.verified = 1 AND a.success = 1 THEN 1 ELSE 0 END)
                    AS verified_successes
            FROM interaction_recipes AS r
            LEFT JOIN recipe_attempts AS a ON a.recipe_id = r.recipe_id
            GROUP BY
                r.recipe_id,
                r.component_fingerprint,
                r.semantic_type,
                r.site_origin,
                r.state,
                r.version,
                r.created_at,
                r.updated_at
            ORDER BY r.updated_at DESC, r.recipe_id
            LIMIT 200
            """
        ).fetchall()
    return [
        {
            "recipeId": str(row["recipe_id"]),
            "componentFingerprint": str(row["component_fingerprint"]),
            "semanticType": str(row["semantic_type"] or "UNKNOWN"),
            "siteOrigin": str(row["site_origin"] or ""),
            "state": str(row["state"]),
            "version": int(row["version"]),
            "verifiedAttempts": int(row["verified_attempts"] or 0),
            "verifiedSuccesses": int(row["verified_successes"] or 0),
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
        }
        for row in rows
    ]


def reliable_handle(
    message: dict[str, object],
    database: Database,
    ai_store: AISettingsStore | None = None,
) -> dict[str, object]:
    if message.get("type") == "LIST_INTERACTION_RECIPES":
        return {"ok": True, "data": list_interaction_recipes(database)}
    return legacy_handle(message, database, ai_store)


def main() -> None:
    settings = Settings.from_environment()
    database = Database(settings.database_path, settings.migrations_path)
    database.migrate()
    ai_store = AISettingsStore(settings.runtime_root)
    while message := read_message(sys.stdin.buffer):
        try:
            write_message(sys.stdout.buffer, reliable_handle(message, database, ai_store))
        except Exception as error:
            write_message(sys.stdout.buffer, {"ok": False, "error": str(error)})


if __name__ == "__main__":
    main()
