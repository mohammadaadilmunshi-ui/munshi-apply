from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import uuid4

from .database import Database


_ACCOUNT_SEMANTICS = {
    "ATS_ACCOUNT_PASSWORD_INPUT",
    "ATS_ACCOUNT_EMAIL_VERIFICATION_CODE",
    "ATS_ACCOUNT_EMAIL_VERIFICATION_LINK",
    "ATS_ACCOUNT_PASSWORD_RESET",
    "ATS_ACCOUNT_MAGIC_LOGIN",
    "ATS_ACCOUNT_CREATE",
    "ATS_ACCOUNT_LOGIN",
}
_ACCOUNT_ACTIONS = {
    "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
    "CONSUME_ONE_TIME_VERIFICATION_CODE",
    "OPEN_VERIFICATION_LINK",
}
_STRUCTURAL_ACTIONS = {"FOCUS", "CLICK", "SELECT_EXACT_OPTION"}
_KEYS = {"ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"}
_WAIT_STATES = {"OPTIONS_VISIBLE", "VALUE_COMMITTED"}
_FORBIDDEN_KEY_MARKERS = (
    "value",
    "password",
    "secret",
    "credential",
    "token",
    "code",
    "otp",
    "url",
    "link",
)


class AccountTeachError(ValueError):
    pass


def _text(value: object, label: str, limit: int = 240) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountTeachError(f"{label} must be a non-empty string")
    clean = value.strip()
    if len(clean) > limit:
        raise AccountTeachError(f"{label} is too long")
    return clean


def _optional(value: object, label: str, limit: int = 240) -> str | None:
    if value is None:
        return None
    return _text(value, label, limit)


def _origin(value: object) -> str:
    raw = _text(value, "siteOrigin", 500)
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AccountTeachError("siteOrigin must be an HTTP(S) origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise AccountTeachError("siteOrigin cannot contain path/query/fragment")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{port}"


def _semantic(value: object) -> str:
    semantic = _text(value, "semanticType", 120).upper()
    if semantic not in _ACCOUNT_SEMANTICS:
        raise AccountTeachError("semanticType is not an approved ATS account mechanic")
    return semantic


def _actions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise AccountTeachError("Account Teach requires 1-16 bounded actions")
    result: list[dict[str, object]] = []
    for action in value:
        if not isinstance(action, dict):
            raise AccountTeachError("Account Teach actions must be objects")
        for key in action:
            lowered = str(key).lower()
            if key != "type" and any(marker in lowered for marker in _FORBIDDEN_KEY_MARKERS):
                raise AccountTeachError("Account Teach actions cannot contain secret/value material")
        action_type = action.get("type")
        if action_type in _ACCOUNT_ACTIONS:
            if set(action) != {"type"}:
                raise AccountTeachError("Resolver actions may contain only their type")
            result.append({"type": str(action_type)})
            continue
        if action_type in _STRUCTURAL_ACTIONS:
            if set(action) != {"type"}:
                raise AccountTeachError("Structural actions may contain only their type")
            result.append({"type": str(action_type)})
            continue
        if action_type == "KEY" and action.get("key") in _KEYS and set(action) == {"type", "key"}:
            result.append({"type": "KEY", "key": str(action["key"])})
            continue
        if (
            action_type == "WAIT_FOR_STATE"
            and action.get("state") in _WAIT_STATES
            and set(action) == {"type", "state"}
        ):
            result.append({"type": "WAIT_FOR_STATE", "state": str(action["state"])})
            continue
        raise AccountTeachError("Unsupported or value-bearing account Teach action")
    return result


def _canonical(actions: list[dict[str, object]]) -> str:
    return json.dumps(actions, sort_keys=True, separators=(",", ":"))


class AccountTeachService:
    """Async Teach path for ATS account mechanics with no secret values.

    This service uses the same interaction_recipes / interaction_recipe_context
    store as ordinary Teach MUNSHI, but has a separate strict queue so generic
    form learning never needs to accept password or verification controls.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def capture(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise AccountTeachError("Account Teach payload must be an object")
        if payload.get("verifiedSuccess") is not True:
            raise AccountTeachError("Only verified successful account mechanics may be learned")
        allowed = {
            "observationId", "applicationId", "siteOrigin", "componentFingerprint",
            "semanticType", "atsFamily", "tenantKey", "uiFingerprint", "actions",
            "verifiedSuccess",
        }
        unexpected = set(payload) - allowed
        if unexpected:
            raise AccountTeachError("Account Teach payload contains unsupported fields")
        observation_id = _text(payload.get("observationId"), "observationId", 160)
        application_id = _optional(payload.get("applicationId"), "applicationId")
        site_origin = _origin(payload.get("siteOrigin"))
        component = _text(payload.get("componentFingerprint"), "componentFingerprint")
        if not component.startswith(("cfp-", "cfp2-")):
            raise AccountTeachError("componentFingerprint is invalid")
        semantic = _semantic(payload.get("semanticType"))
        ats_family = _optional(payload.get("atsFamily"), "atsFamily", 80)
        tenant_key = _optional(payload.get("tenantKey"), "tenantKey")
        ui_fingerprint = _optional(payload.get("uiFingerprint"), "uiFingerprint")
        actions = _actions(payload.get("actions"))
        canonical = {
            "observationId": observation_id,
            "applicationId": application_id,
            "siteOrigin": site_origin,
            "componentFingerprint": component,
            "semanticType": semantic,
            "atsFamily": ats_family.upper() if ats_family else None,
            "tenantKey": tenant_key,
            "uiFingerprint": ui_fingerprint,
            "actions": actions,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        dedupe = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        lesson_id = f"atslesson-{dedupe[:32]}"
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO ats_teach_lessons(
                    lesson_id, dedupe_key, application_id, site_origin,
                    component_fingerprint, semantic_type, ats_family, tenant_key,
                    ui_fingerprint, actions_json, state, attempt_count,
                    created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,'PENDING',0,?,?)
                """,
                (
                    lesson_id, dedupe, application_id, site_origin, component,
                    semantic, canonical["atsFamily"], tenant_key, ui_fingerprint,
                    _canonical(actions), now, now,
                ),
            )
        return {
            "lessonId": lesson_id,
            "queued": True,
            "duplicate": result.rowcount == 0,
            "providerCallMade": False,
            "containsSecretMaterial": False,
        }

    def _lookup(self, row: dict[str, object], *, promoted_only: bool) -> dict[str, object] | None:
        state_clause = "AND r.state='PROMOTED'" if promoted_only else "AND r.state IN ('PROMOTED','SHADOW')"
        with self.database.connect() as connection:
            found = connection.execute(
                f"""
                SELECT r.*, c.ats_family, c.tenant_key, c.ui_fingerprint,
                       c.verified_successes, c.verified_failures,
                       c.consecutive_failures, c.lifecycle_state
                FROM interaction_recipes r
                JOIN interaction_recipe_context c ON c.recipe_id=r.recipe_id
                WHERE r.component_fingerprint=? AND r.semantic_type=? AND r.site_origin=?
                  AND COALESCE(c.ats_family,'')=COALESCE(?, '')
                  AND COALESCE(c.tenant_key,'')=COALESCE(?, '')
                  AND COALESCE(c.ui_fingerprint,'')=COALESCE(?, '')
                  AND c.lifecycle_state='ACTIVE' {state_clause}
                ORDER BY CASE r.state WHEN 'PROMOTED' THEN 0 ELSE 1 END,
                         r.version DESC LIMIT 1
                """,
                (
                    row["component_fingerprint"], row["semantic_type"], row["site_origin"],
                    row.get("ats_family"), row.get("tenant_key"), row.get("ui_fingerprint"),
                ),
            ).fetchone()
        if found is None:
            return None
        result = dict(found)
        result["actions"] = json.loads(str(result.pop("actions_json")))
        return result

    def lookup_promoted(self, payload: object) -> dict[str, object] | None:
        if not isinstance(payload, dict):
            raise AccountTeachError("Recipe lookup payload must be an object")
        row: dict[str, object] = {
            "component_fingerprint": _text(payload.get("componentFingerprint"), "componentFingerprint"),
            "semantic_type": _semantic(payload.get("semanticType")),
            "site_origin": _origin(payload.get("siteOrigin")),
            "ats_family": (_optional(payload.get("atsFamily"), "atsFamily", 80) or "").upper() or None,
            "tenant_key": _optional(payload.get("tenantKey"), "tenantKey"),
            "ui_fingerprint": _optional(payload.get("uiFingerprint"), "uiFingerprint"),
        }
        return self._lookup(row, promoted_only=True)

    def _create_recipe(self, connection: object, row: dict[str, object], actions: list[dict[str, object]], now: str) -> str:
        existing_version = connection.execute(
            """
            SELECT COALESCE(MAX(version),0) FROM interaction_recipes
            WHERE component_fingerprint=? AND semantic_type=? AND site_origin=?
            """,
            (row["component_fingerprint"], row["semantic_type"], row["site_origin"]),
        ).fetchone()[0]
        version = int(existing_version) + 1
        recipe_id = f"recipe-{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO interaction_recipes(
                recipe_id, component_fingerprint, semantic_type, site_origin,
                actions_json, version, state, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,'SHADOW',?,?)
            """,
            (
                recipe_id, row["component_fingerprint"], row["semantic_type"],
                row["site_origin"], _canonical(actions), version, now, now,
            ),
        )
        connection.execute(
            """
            INSERT INTO interaction_recipe_context(
                recipe_id, ats_family, tenant_key, ui_fingerprint,
                question_fingerprint, confidence, verified_successes,
                verified_failures, consecutive_failures, lifecycle_state,
                last_used_at, last_verified_at, created_at, updated_at
            ) VALUES(?,?,?,?,NULL,0.60,1,0,0,'ACTIVE',?,?,?,?)
            """,
            (
                recipe_id, row.get("ats_family"), row.get("tenant_key"),
                row.get("ui_fingerprint"), now, now, now, now,
            ),
        )
        return recipe_id

    def _learn(self, row: dict[str, object]) -> str:
        actions = json.loads(str(row["actions_json"]))
        actions = _actions(actions)
        now = datetime.now(UTC).isoformat()
        existing = self._lookup(row, promoted_only=False)
        with self.database.connect() as connection:
            if existing is None or _canonical(existing["actions"]) != _canonical(actions):
                recipe_id = self._create_recipe(connection, row, actions, now)
            else:
                recipe_id = str(existing["recipe_id"])
                attempt_id = f"ats-teach-{row['lesson_id']}"
                connection.execute(
                    """
                    INSERT OR IGNORE INTO recipe_attempts(
                        attempt_id, recipe_id, application_id, occurred_at,
                        success, verified, failure_reason
                    ) VALUES(?,?,?,?,1,1,NULL)
                    """,
                    (attempt_id, recipe_id, row.get("application_id"), now),
                )
                if connection.execute("SELECT changes()").fetchone()[0]:
                    connection.execute(
                        """
                        UPDATE interaction_recipe_context
                        SET verified_successes=verified_successes+1,
                            consecutive_failures=0, confidence=MIN(1.0, confidence+0.15),
                            last_used_at=?, last_verified_at=?, updated_at=?
                        WHERE recipe_id=?
                        """,
                        (now, now, now, recipe_id),
                    )
            successes = connection.execute(
                "SELECT verified_successes FROM interaction_recipe_context WHERE recipe_id=?",
                (recipe_id,),
            ).fetchone()[0]
            if int(successes) >= 3:
                connection.execute(
                    "UPDATE interaction_recipes SET state='PROMOTED', updated_at=? WHERE recipe_id=? AND state='SHADOW'",
                    (now, recipe_id),
                )
        return recipe_id

    def drain(self, *, limit: int = 20) -> dict[str, object]:
        if not 1 <= int(limit) <= 100:
            raise AccountTeachError("limit must be between 1 and 100")
        learned = 0
        recipe_ids: list[str] = []
        for _ in range(int(limit)):
            now = datetime.now(UTC).isoformat()
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM ats_teach_lessons WHERE state='PENDING' ORDER BY created_at, lesson_id LIMIT 1"
                ).fetchone()
                if row is None:
                    break
                changed = connection.execute(
                    """
                    UPDATE ats_teach_lessons
                    SET state='PROCESSING', attempt_count=attempt_count+1,
                        claimed_at=?, updated_at=?
                    WHERE lesson_id=? AND state='PENDING'
                    """,
                    (now, now, row["lesson_id"]),
                ).rowcount
                if changed != 1:
                    continue
                claimed = dict(connection.execute(
                    "SELECT * FROM ats_teach_lessons WHERE lesson_id=?",
                    (row["lesson_id"],),
                ).fetchone())
            try:
                recipe_id = self._learn(claimed)
                completed = datetime.now(UTC).isoformat()
                with self.database.connect() as connection:
                    connection.execute(
                        """
                        UPDATE ats_teach_lessons
                        SET state='LEARNED', recipe_id=?, completed_at=?, updated_at=?
                        WHERE lesson_id=? AND state='PROCESSING'
                        """,
                        (recipe_id, completed, completed, claimed["lesson_id"]),
                    )
                learned += 1
                recipe_ids.append(recipe_id)
            except (AccountTeachError, ValueError, TypeError) as error:
                completed = datetime.now(UTC).isoformat()
                with self.database.connect() as connection:
                    connection.execute(
                        """
                        UPDATE ats_teach_lessons
                        SET state='SKIPPED', failure_reason=?, completed_at=?, updated_at=?
                        WHERE lesson_id=? AND state='PROCESSING'
                        """,
                        (str(error)[:240], completed, completed, claimed["lesson_id"]),
                    )
        return {"learned": learned, "recipeIds": recipe_ids, "providerCallMade": False}

    def record_verified_outcome(
        self,
        recipe_id: str,
        *,
        application_id: str | None,
        success: bool,
        occurred_at: str,
        failure_reason: str | None = None,
    ) -> dict[str, object]:
        recipe_id = _text(recipe_id, "recipeId")
        now = _text(occurred_at, "occurredAt")
        attempt_id = f"atsoutcome-{uuid4().hex}"
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO recipe_attempts(
                    attempt_id, recipe_id, application_id, occurred_at,
                    success, verified, failure_reason
                ) VALUES(?,?,?,?,?,1,?)
                """,
                (attempt_id, recipe_id, application_id, now, 1 if success else 0, failure_reason),
            )
            if success:
                connection.execute(
                    """
                    UPDATE interaction_recipe_context
                    SET verified_successes=verified_successes+1, consecutive_failures=0,
                        confidence=MIN(1.0, confidence+0.15), last_used_at=?,
                        last_verified_at=?, updated_at=? WHERE recipe_id=?
                    """,
                    (now, now, now, recipe_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE interaction_recipe_context
                    SET verified_failures=verified_failures+1,
                        consecutive_failures=consecutive_failures+1,
                        confidence=MAX(0.0, confidence-0.25), last_used_at=?,
                        last_verified_at=?, updated_at=? WHERE recipe_id=?
                    """,
                    (now, now, now, recipe_id),
                )
                failures = connection.execute(
                    "SELECT consecutive_failures FROM interaction_recipe_context WHERE recipe_id=?",
                    (recipe_id,),
                ).fetchone()[0]
                if int(failures) >= 2:
                    connection.execute(
                        "UPDATE interaction_recipes SET state='ROLLED_BACK', updated_at=? WHERE recipe_id=?",
                        (now, recipe_id),
                    )
                    connection.execute(
                        """
                        UPDATE interaction_recipe_context
                        SET lifecycle_state='QUARANTINED', quarantined_at=?,
                            quarantine_reason='verified_account_recipe_failures', updated_at=?
                        WHERE recipe_id=?
                        """,
                        (now, now, recipe_id),
                    )
            recipe = connection.execute(
                "SELECT state FROM interaction_recipes WHERE recipe_id=?",
                (recipe_id,),
            ).fetchone()
            context = connection.execute(
                "SELECT * FROM interaction_recipe_context WHERE recipe_id=?",
                (recipe_id,),
            ).fetchone()
        if recipe is None or context is None:
            raise AccountTeachError("Unknown account recipe")
        return {"recipeId": recipe_id, "state": recipe[0], **dict(context)}
