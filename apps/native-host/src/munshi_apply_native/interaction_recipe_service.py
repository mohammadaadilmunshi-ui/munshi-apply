from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from .database import Database
from .learning_analytics_store import LearningAnalyticsStore

_ALLOWED_STRATEGIES = {
    "ARIA_COMBOBOX",
    "ARIA_RADIO",
    "ARIA_BOOLEAN",
    "CUSTOM_DATE",
    "CUSTOM_MULTI_SELECT",
}
_BLOCKED_SEMANTIC_MARKERS = {
    "AUTHORIZATION",
    "SPONSORSHIP",
    "DEMOGRAPHIC",
    "DISABILITY",
    "VETERAN",
    "SALARY",
    "COMPENSATION",
    "SECURITY",
    "BACKGROUND",
    "DISCLOSURE",
    "PASSWORD",
    "OTP",
    "MFA",
}
_ACTIONS: dict[str, list[dict[str, object]]] = {
    "ARIA_COMBOBOX": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "ARIA_RADIO": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "ARIA_BOOLEAN": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "CUSTOM_DATE": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
    "CUSTOM_MULTI_SELECT": [
        {"type": "FOCUS"},
        {"type": "CLICK"},
        {"type": "WAIT_FOR_STATE", "state": "OPTIONS_VISIBLE"},
        {"type": "SELECT_EXACT_OPTION"},
        {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
    ],
}


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _site_origin(payload: dict[str, Any]) -> str:
    origin = _required(payload, "siteOrigin")
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("siteOrigin must be an http(s) origin")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("siteOrigin must not contain a path, query, or fragment")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{port}"


def _binding(payload: dict[str, Any]) -> tuple[str, str, str]:
    origin = _site_origin(payload)
    fingerprint = _required(payload, "componentFingerprint")
    if not fingerprint.startswith("cfp-"):
        raise ValueError("componentFingerprint is invalid")
    semantic_type = _required(payload, "semanticType").upper()
    if any(marker in semantic_type for marker in _BLOCKED_SEMANTIC_MARKERS):
        raise ValueError("Sensitive or consequential semantics cannot create interaction recipes")
    return origin, fingerprint, semantic_type


def _strategy(payload: dict[str, Any]) -> str:
    strategy = _required(payload, "strategy").upper()
    if strategy not in _ALLOWED_STRATEGIES:
        raise ValueError("Interaction strategy is not eligible for learning")
    return strategy


def _recipe_id(origin: str, fingerprint: str, semantic_type: str, strategy: str) -> str:
    digest = hashlib.sha256(
        f"{origin}\n{fingerprint}\n{semantic_type}\n{strategy}".encode()
    ).hexdigest()[:32]
    return f"recipe-{digest}"


def _wire_recipe(row: dict[str, Any], strategy: str) -> dict[str, object]:
    return {
        "recipeId": row["recipe_id"],
        "componentFingerprint": row["component_fingerprint"],
        "semanticType": row["semantic_type"],
        "siteOrigin": row["site_origin"],
        "strategy": strategy,
        "state": row["state"],
        "version": row["version"],
        "actions": row["actions"],
    }


class InteractionRecipeService:
    """Learns only verified widget mechanics; never stores application answer values."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.store = LearningAnalyticsStore(database)

    def lookup(self, payload: object) -> dict[str, object] | None:
        if not isinstance(payload, dict):
            raise ValueError("Recipe lookup payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT recipe_id
                FROM interaction_recipes
                WHERE site_origin = ? AND component_fingerprint = ?
                  AND semantic_type = ? AND state = 'PROMOTED'
                ORDER BY recipe_id
                """,
                (origin, fingerprint, semantic_type),
            ).fetchall()
        if len(rows) != 1:
            return None
        recipe = self.store.recipe(str(rows[0]["recipe_id"]))
        if recipe is None:
            return None
        strategy = self._strategy_for_actions(recipe["actions"])
        if strategy is None:
            return None
        return _wire_recipe(recipe, strategy)

    @staticmethod
    def _strategy_for_actions(actions: object) -> str | None:
        if not isinstance(actions, list):
            return None
        for strategy, expected in _ACTIONS.items():
            if actions == expected:
                return strategy
        return None

    def record(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Recipe attempt payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        strategy = _strategy(payload)
        attempt_id = _required(payload, "attemptId")
        application_id = payload.get("applicationId")
        if application_id is not None and (
            not isinstance(application_id, str) or not application_id.strip()
        ):
            raise ValueError("applicationId must be a non-empty string when supplied")
        success = payload.get("success")
        verified = payload.get("verified")
        if not isinstance(success, bool) or not isinstance(verified, bool):
            raise ValueError("Recipe attempt success and verified must be booleans")
        failure_reason = payload.get("failureReason")
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError("failureReason must be a string or null")

        recipe_id = _recipe_id(origin, fingerprint, semantic_type, strategy)
        now = datetime.now(UTC).isoformat()
        existing = self.store.recipe(recipe_id)
        if existing is None:
            self.store.save_recipe(
                {
                    "recipe_id": recipe_id,
                    "component_fingerprint": fingerprint,
                    "semantic_type": semantic_type,
                    "site_origin": origin,
                    "actions": _ACTIONS[strategy],
                    "version": 1,
                    "state": "SHADOW",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            existing = self.store.recipe(recipe_id)
        if existing is None:
            raise RuntimeError("Interaction recipe could not be initialized")

        inserted = self.store.record_recipe_attempt(
            {
                "attempt_id": attempt_id,
                "recipe_id": recipe_id,
                "application_id": application_id.strip()
                if isinstance(application_id, str)
                else None,
                "occurred_at": now,
                "success": success,
                "verified": verified,
                "failure_reason": failure_reason.strip()
                if isinstance(failure_reason, str) and failure_reason.strip()
                else None,
            }
        )
        attempts = self.store.recipe_attempts(recipe_id)
        state = str(existing["state"])
        verified_attempts = [item for item in attempts if item["verified"]]

        if state == "SHADOW" and len(verified_attempts) >= 3:
            if all(bool(item["success"]) for item in verified_attempts[-3:]):
                state = "PROMOTED"
        elif state == "PROMOTED" and len(verified_attempts) >= 2:
            if all(not bool(item["success"]) for item in verified_attempts[-2:]):
                state = "ROLLED_BACK"

        if state != existing["state"]:
            self.store.save_recipe(
                {
                    "recipe_id": existing["recipe_id"],
                    "component_fingerprint": existing["component_fingerprint"],
                    "semantic_type": existing["semantic_type"],
                    "site_origin": existing["site_origin"],
                    "actions": existing["actions"],
                    "version": existing["version"],
                    "state": state,
                    "created_at": existing["created_at"],
                    "updated_at": now,
                }
            )
        final = self.store.recipe(recipe_id)
        if final is None:
            raise RuntimeError("Interaction recipe disappeared")
        return {
            **_wire_recipe(final, strategy),
            "attemptInserted": inserted,
            "verifiedAttempts": len(verified_attempts),
            "verifiedSuccesses": sum(bool(item["success"]) for item in verified_attempts),
        }
