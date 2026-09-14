from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from .database import Database
from .interaction_knowledge_store import InteractionKnowledgeStore, normalized_context
from .learning_analytics_store import LearningAnalyticsStore

_ALLOWED_STRATEGIES = {
    "ARIA_COMBOBOX",
    "ARIA_RADIO",
    "ARIA_BOOLEAN",
    "CUSTOM_DATE",
    "CUSTOM_MULTI_SELECT",
}
_BLOCKED_SEMANTIC_MARKERS = {
    "PASSWORD",
    "OTP",
    "MFA",
    "CAPTCHA",
    "IDENTITY_VERIFICATION",
    "AUTHENTICATION",
    "SUBMIT",
    "GOVERNMENT_ID",
    "SMS",
}
_ALLOWED_KEYS = {"ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"}
_ALLOWED_WAIT_STATES = {"OPTIONS_VISIBLE", "VALUE_COMMITTED"}
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
        raise ValueError("Authentication/security controls cannot create interaction recipes")
    return origin, fingerprint, semantic_type


def _strategy(payload: dict[str, Any]) -> str:
    strategy = _required(payload, "strategy").upper()
    if strategy not in _ALLOWED_STRATEGIES:
        raise ValueError("Interaction strategy is not eligible for learning")
    return strategy


def _validate_actions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise ValueError("Taught recipe requires 1-16 actions")
    result: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("Taught recipe actions must be objects")
        action_type = raw.get("type")
        if action_type in {"FOCUS", "CLICK", "SELECT_EXACT_OPTION"}:
            result.append({"type": action_type})
            continue
        if action_type == "TYPE" and raw.get("valueSource") == "ANSWER":
            result.append({"type": "TYPE", "valueSource": "ANSWER"})
            continue
        if action_type == "KEY" and raw.get("key") in _ALLOWED_KEYS:
            result.append({"type": "KEY", "key": raw["key"]})
            continue
        if action_type == "WAIT_FOR_STATE" and raw.get("state") in _ALLOWED_WAIT_STATES:
            result.append({"type": "WAIT_FOR_STATE", "state": raw["state"]})
            continue
        raise ValueError("Taught recipe contains an unsupported or value-bearing action")
    return result


def _context_identity(payload: dict[str, Any]) -> str:
    context = normalized_context(payload)
    keys = (
        "ats_family",
        "tenant_key",
        "ui_fingerprint",
        "question_fingerprint",
    )
    values = [context[key] or "" for key in keys]
    return "\n".join(values) if any(values) else ""


def _recipe_id(
    origin: str,
    fingerprint: str,
    semantic_type: str,
    strategy: str,
    context_identity: str = "",
) -> str:
    base = f"{origin}\n{fingerprint}\n{semantic_type}\n{strategy}"
    if context_identity:
        base = f"{base}\ncontext\n{context_identity}"
    digest = hashlib.sha256(base.encode()).hexdigest()[:32]
    return f"recipe-{digest}"


def _taught_recipe_id(
    origin: str,
    fingerprint: str,
    semantic_type: str,
    version: int,
    actions: list[dict[str, object]],
    context_identity: str = "",
) -> str:
    canonical = json.dumps(actions, sort_keys=True, separators=(",", ":"))
    base = f"{origin}\n{fingerprint}\n{semantic_type}\n{version}\n{canonical}"
    if context_identity:
        base = f"{base}\ncontext\n{context_identity}"
    digest = hashlib.sha256(base.encode()).hexdigest()[:32]
    return f"recipe-{digest}"


def _strategy_for_actions(actions: object) -> str | None:
    if not isinstance(actions, list):
        return None
    for strategy, expected in _ACTIONS.items():
        if actions == expected:
            return strategy
    try:
        _validate_actions(actions)
    except ValueError:
        return None
    return "TAUGHT_RECIPE"


def _wire_recipe(
    row: dict[str, Any],
    strategy: str,
    context: dict[str, Any] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "recipeId": row["recipe_id"],
        "componentFingerprint": row["component_fingerprint"],
        "semanticType": row["semantic_type"],
        "siteOrigin": row["site_origin"],
        "strategy": strategy,
        "state": row["state"],
        "version": row["version"],
        "actions": row["actions"],
    }
    if context is not None:
        result.update(
            {
                "atsFamily": context.get("ats_family"),
                "tenantKey": context.get("tenant_key"),
                "uiFingerprint": context.get("ui_fingerprint"),
                "questionFingerprint": context.get("question_fingerprint"),
                "confidence": context.get("confidence"),
                "knowledgeState": context.get("lifecycle_state"),
            }
        )
    return result


class InteractionRecipeService:
    """Learns verified widget mechanics without storing application answer values."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.store = LearningAnalyticsStore(database)
        self.knowledge = InteractionKnowledgeStore(database)

    def lookup(self, payload: object) -> dict[str, object] | None:
        if not isinstance(payload, dict):
            raise ValueError("Recipe lookup payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        normalized_context(payload)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT recipe_id
                FROM interaction_recipes
                WHERE site_origin = ? AND component_fingerprint = ?
                  AND semantic_type = ? AND state IN ('PROMOTED', 'SHADOW')
                ORDER BY CASE state WHEN 'PROMOTED' THEN 0 ELSE 1 END,
                         version DESC, updated_at DESC
                """,
                (origin, fingerprint, semantic_type),
            ).fetchall()
        for row in rows:
            recipe_id = str(row["recipe_id"])
            if not self.knowledge.compatible(recipe_id, payload):
                continue
            recipe = self.store.recipe(recipe_id)
            if recipe is None:
                continue
            strategy = _strategy_for_actions(recipe["actions"])
            if strategy is not None:
                attempts = self.store.recipe_attempts(recipe_id)
                verified_attempts = [item for item in attempts if item["verified"]]
                return {
                    **_wire_recipe(
                        recipe,
                        strategy,
                        self.knowledge.context(recipe_id),
                    ),
                    "verifiedAttempts": len(verified_attempts),
                    "verifiedSuccesses": sum(
                        bool(item["success"]) for item in verified_attempts
                    ),
                    "verifiedFailures": sum(
                        not bool(item["success"]) for item in verified_attempts
                    ),
                }
        return None

    def _finalize_state(self, recipe_id: str) -> dict[str, object]:
        recipe = self.store.recipe(recipe_id)
        if recipe is None:
            raise RuntimeError("Interaction recipe disappeared")
        strategy = _strategy_for_actions(recipe["actions"])
        if strategy is None:
            raise ValueError("Stored interaction recipe is invalid")
        attempts = self.store.recipe_attempts(recipe_id)
        verified_attempts = [item for item in attempts if item["verified"]]
        state = str(recipe["state"])
        knowledge = self.knowledge.context(recipe_id)

        # Every learned mechanic, regardless of the teacher provider, needs three
        # independently verified successes before deterministic promotion.
        promotion_threshold = 3
        if knowledge is not None and knowledge["lifecycle_state"] == "QUARANTINED":
            if state in {"SHADOW", "PROMOTED"}:
                state = "ROLLED_BACK"
        elif state == "SHADOW" and len(verified_attempts) >= promotion_threshold:
            recent = verified_attempts[-promotion_threshold:]
            if all(bool(item["success"]) for item in recent):
                state = "PROMOTED"
        elif state == "PROMOTED" and len(verified_attempts) >= 2:
            if all(not bool(item["success"]) for item in verified_attempts[-2:]):
                state = "ROLLED_BACK"

        if state != recipe["state"]:
            now = datetime.now(UTC).isoformat()
            self.store.save_recipe(
                {
                    "recipe_id": recipe["recipe_id"],
                    "component_fingerprint": recipe["component_fingerprint"],
                    "semantic_type": recipe["semantic_type"],
                    "site_origin": recipe["site_origin"],
                    "actions": recipe["actions"],
                    "version": recipe["version"],
                    "state": state,
                    "created_at": recipe["created_at"],
                    "updated_at": now,
                }
            )
            recipe = self.store.recipe(recipe_id)
            if recipe is None:
                raise RuntimeError("Interaction recipe disappeared after state update")
        knowledge = self.knowledge.context(recipe_id)
        return {
            **_wire_recipe(recipe, strategy, knowledge),
            "verifiedAttempts": len(verified_attempts),
            "verifiedSuccesses": sum(bool(item["success"]) for item in verified_attempts),
            "verifiedFailures": sum(
                not bool(item["success"]) for item in verified_attempts
            ),
        }

    def _record_outcome(
        self,
        recipe_id: str,
        *,
        attempt_id: str,
        application_id: str | None,
        success: bool,
        verified: bool,
        failure_reason: str | None,
    ) -> dict[str, object]:
        if self.store.recipe(recipe_id) is None:
            raise ValueError("Interaction recipe does not exist")
        now = datetime.now(UTC).isoformat()
        inserted = self.store.record_recipe_attempt(
            {
                "attempt_id": attempt_id,
                "recipe_id": recipe_id,
                "application_id": application_id,
                "occurred_at": now,
                "success": success,
                "verified": verified,
                "failure_reason": failure_reason,
            }
        )
        if inserted:
            self.knowledge.record_recipe_health(
                recipe_id,
                success=success,
                verified=verified,
                failure_reason=failure_reason,
                at=now,
            )
        return {**self._finalize_state(recipe_id), "attemptInserted": inserted}

    def teach(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Teach MUNSHI payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        actions = _validate_actions(payload.get("actions"))
        context_identity = _context_identity(payload)
        attempt_id = _required(payload, "attemptId")
        application_id = payload.get("applicationId")
        if application_id is not None and (
            not isinstance(application_id, str) or not application_id.strip()
        ):
            raise ValueError("applicationId must be a non-empty string when supplied")
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS version
                FROM interaction_recipes
                WHERE site_origin = ? AND component_fingerprint = ? AND semantic_type = ?
                """,
                (origin, fingerprint, semantic_type),
            ).fetchone()
        version = int(row["version"] if row is not None else 0) + 1
        now = datetime.now(UTC).isoformat()
        recipe_id = _taught_recipe_id(
            origin,
            fingerprint,
            semantic_type,
            version,
            actions,
            context_identity,
        )
        self.store.save_recipe(
            {
                "recipe_id": recipe_id,
                "component_fingerprint": fingerprint,
                "semantic_type": semantic_type,
                "site_origin": origin,
                "actions": actions,
                "version": version,
                "state": "SHADOW",
                "created_at": now,
                "updated_at": now,
            }
        )
        self.knowledge.upsert_context(recipe_id, payload, at=now)
        return self._record_outcome(
            recipe_id,
            attempt_id=attempt_id,
            application_id=(
                application_id.strip() if isinstance(application_id, str) else None
            ),
            success=True,
            verified=True,
            failure_reason=None,
        )

    def record_outcome(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Recipe outcome payload must be an object")
        recipe_id = _required(payload, "recipeId")
        attempt_id = _required(payload, "attemptId")
        application_id = payload.get("applicationId")
        if application_id is not None and (
            not isinstance(application_id, str) or not application_id.strip()
        ):
            raise ValueError("applicationId must be a non-empty string when supplied")
        success = payload.get("success")
        verified = payload.get("verified")
        if not isinstance(success, bool) or not isinstance(verified, bool):
            raise ValueError("Recipe outcome success and verified must be booleans")
        failure_reason = payload.get("failureReason")
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError("failureReason must be a string or null")
        return self._record_outcome(
            recipe_id,
            attempt_id=attempt_id,
            application_id=(
                application_id.strip() if isinstance(application_id, str) else None
            ),
            success=success,
            verified=verified,
            failure_reason=(
                failure_reason.strip()
                if isinstance(failure_reason, str) and failure_reason.strip()
                else None
            ),
        )

    def record(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Recipe attempt payload must be an object")
        origin, fingerprint, semantic_type = _binding(payload)
        strategy = _strategy(payload)
        context_identity = _context_identity(payload)
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
        recipe_id = _recipe_id(
            origin,
            fingerprint,
            semantic_type,
            strategy,
            context_identity,
        )
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
        self.knowledge.upsert_context(recipe_id, payload, at=now)
        return self._record_outcome(
            recipe_id,
            attempt_id=attempt_id,
            application_id=(
                application_id.strip() if isinstance(application_id, str) else None
            ),
            success=success,
            verified=verified,
            failure_reason=(
                failure_reason.strip()
                if isinstance(failure_reason, str) and failure_reason.strip()
                else None
            ),
        )

    def record_resolution(self, payload: object) -> bool:
        if not isinstance(payload, dict):
            raise ValueError("Resolution telemetry payload must be an object")
        return self.knowledge.record_resolution(payload)

    def cost_summary(self, *, since: str | None = None) -> dict[str, object]:
        return self.knowledge.cost_summary(since=since)
