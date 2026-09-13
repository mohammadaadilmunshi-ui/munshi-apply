from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .database import Database

_RESOLUTION_LANES = {
    "PROMOTED_RECIPE",
    "SHADOW_RECIPE",
    "NATIVE_CONTROL",
    "ARIA_PATTERN",
    "KEYBOARD_PATTERN",
    "STRUCTURAL_POPUP",
    "STATE_TRANSITION",
    "LOCAL_SEMANTIC_HINT",
    "MODEL_RECIPE_PROPOSAL",
    # Kept for compatibility with pre-generalization telemetry.
    "CLAUDE_RECIPE_PROPOSAL",
    "VISUAL_ASSISTED_CONTROL",
}
_RECIPE_LANES = {"PROMOTED_RECIPE", "SHADOW_RECIPE"}
_MODEL_LANES = {"MODEL_RECIPE_PROPOSAL", "CLAUDE_RECIPE_PROPOSAL"}
_AI_LANES = {
    "LOCAL_SEMANTIC_HINT",
    "MODEL_RECIPE_PROPOSAL",
    "CLAUDE_RECIPE_PROPOSAL",
    "VISUAL_ASSISTED_CONTROL",
}
_CONTEXT_FIELDS = (
    ("ats_family", "atsFamily", 80),
    ("tenant_key", "tenantKey", 240),
    ("ui_fingerprint", "uiFingerprint", 240),
    ("question_fingerprint", "questionFingerprint", 240),
)


def _optional_text(value: object, *, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "Interaction context values must be non-empty strings when supplied"
        )
    clean = value.strip()
    if len(clean) > limit:
        raise ValueError("Interaction context value is too long")
    return clean


def normalized_context(payload: dict[str, Any]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for column, wire, limit in _CONTEXT_FIELDS:
        value = _optional_text(payload.get(wire), limit=limit)
        if column == "ats_family" and value is not None:
            value = value.upper()
        result[column] = value
    return result


class InteractionKnowledgeStore:
    """Persistent mechanics knowledge and resolution-cost telemetry.

    No answer values, passwords, OTPs, candidate facts, or form responses are
    accepted by this store. It records only UI mechanics/context fingerprints and
    execution outcomes.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def context(self, recipe_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM interaction_recipe_context WHERE recipe_id = ?",
                (recipe_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def upsert_context(
        self,
        recipe_id: str,
        payload: dict[str, Any],
        *,
        at: str | None = None,
    ) -> dict[str, Any]:
        context = normalized_context(payload)
        now = at or datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            recipe = connection.execute(
                "SELECT recipe_id FROM interaction_recipes WHERE recipe_id = ?",
                (recipe_id,),
            ).fetchone()
            if recipe is None:
                raise ValueError("Interaction recipe does not exist")
            existing = connection.execute(
                "SELECT * FROM interaction_recipe_context WHERE recipe_id = ?",
                (recipe_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO interaction_recipe_context(
                        recipe_id, ats_family, tenant_key, ui_fingerprint,
                        question_fingerprint, confidence, verified_successes,
                        verified_failures, consecutive_failures, lifecycle_state,
                        last_used_at, last_verified_at, quarantined_at,
                        quarantine_reason, created_at, updated_at
                    ) VALUES(
                        ?, ?, ?, ?, ?, 0.50, 0, 0, 0, 'ACTIVE',
                        NULL, NULL, NULL, NULL, ?, ?
                    )
                    """,
                    (
                        recipe_id,
                        context["ats_family"],
                        context["tenant_key"],
                        context["ui_fingerprint"],
                        context["question_fingerprint"],
                        now,
                        now,
                    ),
                )
            else:
                for column, _, _ in _CONTEXT_FIELDS:
                    requested = context[column]
                    current = existing[column]
                    if requested is not None and current not in {None, requested}:
                        raise ValueError("Interaction recipe context cannot be rebound")
                connection.execute(
                    """
                    UPDATE interaction_recipe_context
                    SET ats_family=COALESCE(ats_family, ?),
                        tenant_key=COALESCE(tenant_key, ?),
                        ui_fingerprint=COALESCE(ui_fingerprint, ?),
                        question_fingerprint=COALESCE(question_fingerprint, ?),
                        updated_at=?
                    WHERE recipe_id=?
                    """,
                    (
                        context["ats_family"],
                        context["tenant_key"],
                        context["ui_fingerprint"],
                        context["question_fingerprint"],
                        now,
                        recipe_id,
                    ),
                )
            row = connection.execute(
                "SELECT * FROM interaction_recipe_context WHERE recipe_id = ?",
                (recipe_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Interaction recipe context was not persisted")
        return dict(row)

    def compatible(self, recipe_id: str, payload: dict[str, Any]) -> bool:
        requested = normalized_context(payload)
        stored = self.context(recipe_id)
        if stored is None:
            # Backward compatibility for recipes created before migration 021.
            return True
        if stored["lifecycle_state"] == "QUARANTINED":
            return False
        for column, _, _ in _CONTEXT_FIELDS:
            expected = stored[column]
            observed = requested[column]
            if expected is not None and observed is not None and expected != observed:
                return False
        return True

    def record_recipe_health(
        self,
        recipe_id: str,
        *,
        success: bool,
        verified: bool,
        failure_reason: str | None,
        at: str | None = None,
        quarantine_after_failures: int = 2,
    ) -> dict[str, Any]:
        if quarantine_after_failures < 1:
            raise ValueError("quarantine_after_failures must be positive")
        now = at or datetime.now(UTC).isoformat()
        existing = self.context(recipe_id)
        if existing is None:
            existing = self.upsert_context(recipe_id, {}, at=now)
        if not verified:
            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE interaction_recipe_context
                    SET last_used_at=?, updated_at=?
                    WHERE recipe_id=?
                    """,
                    (now, now, recipe_id),
                )
            refreshed = self.context(recipe_id)
            if refreshed is None:
                raise RuntimeError("Interaction recipe context disappeared")
            return refreshed

        successes = int(existing["verified_successes"]) + (1 if success else 0)
        failures = int(existing["verified_failures"]) + (0 if success else 1)
        consecutive = 0 if success else int(existing["consecutive_failures"]) + 1
        confidence = round((successes + 1) / (successes + failures + 2), 6)
        lifecycle = str(existing["lifecycle_state"])
        quarantined_at = existing["quarantined_at"]
        quarantine_reason = existing["quarantine_reason"]
        if consecutive >= quarantine_after_failures:
            lifecycle = "QUARANTINED"
            quarantined_at = now
            quarantine_reason = (failure_reason or "repeated_verified_failure")[:240]

        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE interaction_recipe_context
                SET confidence=?, verified_successes=?, verified_failures=?,
                    consecutive_failures=?, lifecycle_state=?, last_used_at=?,
                    last_verified_at=?, quarantined_at=?, quarantine_reason=?,
                    updated_at=?
                WHERE recipe_id=?
                """,
                (
                    confidence,
                    successes,
                    failures,
                    consecutive,
                    lifecycle,
                    now,
                    now,
                    quarantined_at,
                    quarantine_reason,
                    now,
                    recipe_id,
                ),
            )
        refreshed = self.context(recipe_id)
        if refreshed is None:
            raise RuntimeError("Interaction recipe context disappeared")
        return refreshed

    def record_resolution(self, event: dict[str, Any]) -> bool:
        event_id = str(event.get("event_id") or "").strip()
        site_origin = str(event.get("site_origin") or "").strip()
        lane = str(event.get("resolution_lane") or "").strip().upper()
        occurred_at = str(event.get("occurred_at") or "").strip()
        if not event_id or not site_origin or not occurred_at:
            raise ValueError("Resolution event requires id, site origin, and timestamp")
        if lane not in _RESOLUTION_LANES:
            raise ValueError("Resolution lane is invalid")
        success = event.get("success")
        verified = event.get("verified")
        if not isinstance(success, bool) or not isinstance(verified, bool):
            raise ValueError("Resolution success and verified must be booleans")
        input_tokens = int(event.get("input_tokens") or 0)
        output_tokens = int(event.get("output_tokens") or 0)
        cost = float(event.get("ai_cost_usd") or 0.0)
        if input_tokens < 0 or output_tokens < 0 or cost < 0:
            raise ValueError("Resolution AI usage cannot be negative")
        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO interaction_resolution_events(
                    event_id, application_id, site_origin, component_fingerprint,
                    semantic_type, recipe_id, resolution_lane, success, verified,
                    ai_provider, ai_model, input_tokens, output_tokens, ai_cost_usd,
                    fallback_reason, occurred_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_id,
                    event.get("application_id"),
                    site_origin,
                    event.get("component_fingerprint"),
                    event.get("semantic_type"),
                    event.get("recipe_id"),
                    lane,
                    1 if success else 0,
                    1 if verified else 0,
                    event.get("ai_provider"),
                    event.get("ai_model"),
                    input_tokens,
                    output_tokens,
                    round(cost, 8),
                    event.get("fallback_reason"),
                    occurred_at,
                ),
            )
        return result.rowcount == 1

    @staticmethod
    def _totals_sql(*, filtered: bool) -> str:
        base = """
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT application_id) AS applications,
                   COALESCE(SUM(ai_cost_usd),0) AS cost,
                   COALESCE(SUM(input_tokens),0) AS input_tokens,
                   COALESCE(SUM(output_tokens),0) AS output_tokens,
                   COALESCE(SUM(
                       CASE WHEN resolution_lane IN (
                           'MODEL_RECIPE_PROPOSAL','CLAUDE_RECIPE_PROPOSAL'
                       ) THEN 1 ELSE 0 END
                   ),0) AS model_fallbacks,
                   COALESCE(SUM(
                       CASE WHEN resolution_lane='CLAUDE_RECIPE_PROPOSAL'
                       THEN 1 ELSE 0 END
                   ),0) AS legacy_claude,
                   COALESCE(SUM(
                       CASE WHEN resolution_lane IN (
                           'PROMOTED_RECIPE','SHADOW_RECIPE'
                       ) THEN 1 ELSE 0 END
                   ),0) AS recipes,
                   COALESCE(SUM(
                       CASE WHEN resolution_lane NOT IN (
                           'LOCAL_SEMANTIC_HINT','MODEL_RECIPE_PROPOSAL',
                           'CLAUDE_RECIPE_PROPOSAL','VISUAL_ASSISTED_CONTROL'
                       ) THEN 1 ELSE 0 END
                   ),0) AS deterministic
            FROM interaction_resolution_events
        """
        return base + (" WHERE occurred_at >= ?" if filtered else "")

    @staticmethod
    def _lanes_sql(*, filtered: bool) -> str:
        base = """
            SELECT resolution_lane, COUNT(*) AS count,
                   COALESCE(SUM(ai_cost_usd),0) AS cost
            FROM interaction_resolution_events
        """
        suffix = " WHERE occurred_at >= ?" if filtered else ""
        return base + suffix + " GROUP BY resolution_lane ORDER BY count DESC, resolution_lane"

    @staticmethod
    def _providers_sql(*, filtered: bool) -> str:
        base = """
            SELECT COALESCE(ai_provider,'none') AS provider,
                   COUNT(*) AS count,
                   COALESCE(SUM(ai_cost_usd),0) AS cost,
                   COALESCE(SUM(input_tokens),0) AS input_tokens,
                   COALESCE(SUM(output_tokens),0) AS output_tokens
            FROM interaction_resolution_events
            WHERE ai_provider IS NOT NULL
        """
        suffix = " AND occurred_at >= ?" if filtered else ""
        return base + suffix + " GROUP BY ai_provider ORDER BY count DESC, ai_provider"

    def cost_summary(self, *, since: str | None = None) -> dict[str, object]:
        filtered = bool(since)
        parameters: tuple[object, ...] = (since,) if since else ()
        with self.database.connect() as connection:
            totals = connection.execute(
                self._totals_sql(filtered=filtered),
                parameters,
            ).fetchone()
            lanes = connection.execute(
                self._lanes_sql(filtered=filtered),
                parameters,
            ).fetchall()
            providers = connection.execute(
                self._providers_sql(filtered=filtered),
                parameters,
            ).fetchall()
        total = int(totals["total"])
        applications = int(totals["applications"])
        cost = round(float(totals["cost"]), 8)
        model_fallbacks = int(totals["model_fallbacks"])
        return {
            "totalResolutions": total,
            "applications": applications,
            "deterministicResolutionRate": (
                round(int(totals["deterministic"]) / total, 6) if total else 0.0
            ),
            "recipeHitRate": (
                round(int(totals["recipes"]) / total, 6) if total else 0.0
            ),
            "modelFallbackRate": (
                round(model_fallbacks / total, 6) if total else 0.0
            ),
            "claudeFallbackRate": (
                round(int(totals["legacy_claude"]) / total, 6) if total else 0.0
            ),
            "aiCostUsd": cost,
            "aiCostPerApplicationUsd": (
                round(cost / applications, 8) if applications else 0.0
            ),
            "inputTokens": int(totals["input_tokens"]),
            "outputTokens": int(totals["output_tokens"]),
            "lanes": [dict(row) for row in lanes],
            "providers": [dict(row) for row in providers],
        }

    def prune_resolution_events(
        self,
        *,
        retention_days: int = 90,
        at: str | None = None,
    ) -> int:
        if not 30 <= retention_days <= 3650:
            raise ValueError(
                "Resolution telemetry retention must be between 30 and 3650 days"
            )
        now = (
            datetime.fromisoformat(at.replace("Z", "+00:00"))
            if at
            else datetime.now(UTC)
        )
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        cutoff = (now.astimezone(UTC) - timedelta(days=retention_days)).isoformat()
        with self.database.connect() as connection:
            result = connection.execute(
                "DELETE FROM interaction_resolution_events WHERE occurred_at < ?",
                (cutoff,),
            )
        return result.rowcount


def is_ai_lane(lane: str) -> bool:
    return lane.upper() in _AI_LANES


def is_recipe_lane(lane: str) -> bool:
    return lane.upper() in _RECIPE_LANES


def is_model_lane(lane: str) -> bool:
    return lane.upper() in _MODEL_LANES
