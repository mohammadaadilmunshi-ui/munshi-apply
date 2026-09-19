from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from .database import Database
from .interaction_recipe_service import InteractionRecipeService
from .mechanics_actions import MechanicsActionError, validate_mechanics_actions

_TEACHER_KINDS = {
    "MODEL",
    "LOCAL_MODEL",
    "DETERMINISTIC_RECOVERY",
    "USER_DEMONSTRATION",
    "EXISTING_RECIPE",
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
_MAX_ATTEMPTS = 3


class TeachMunshiError(ValueError):
    """A lesson cannot safely enter the Teach MUNSHI pipeline."""


def _required_text(value: object, label: str, *, limit: int = 240) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TeachMunshiError(f"{label} must be a non-empty string")
    clean = value.strip()
    if len(clean) > limit:
        raise TeachMunshiError(f"{label} is too long")
    return clean


def _optional_text(value: object, label: str, *, limit: int = 240) -> str | None:
    if value is None:
        return None
    return _required_text(value, label, limit=limit)


def _origin(value: object) -> str:
    raw = _required_text(value, "siteOrigin", limit=500)
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TeachMunshiError("siteOrigin must be an HTTP(S) origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise TeachMunshiError("siteOrigin cannot contain a path, query, or fragment")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{port}"


def _semantic(value: object) -> str:
    semantic = _required_text(value, "semanticType", limit=120).upper()
    if any(marker in semantic for marker in _BLOCKED_SEMANTIC_MARKERS):
        raise TeachMunshiError(
            "Authentication/security controls cannot become Teach MUNSHI lessons"
        )
    return semantic


def _actions(value: object) -> list[dict[str, object]]:
    if isinstance(value, list) and any(
        isinstance(item, dict)
        and (
            "targetRef" in item
            or "answerRef" in item
            or "artifactRef" in item
            or "valueRef" in item
            or str(item.get("type") or "").upper()
            in {"NEXT", "TYPE_ANSWER_REF", "UPLOAD_ARTIFACT", "SELECT"}
        )
        for item in value
    ):
        try:
            return validate_mechanics_actions(value)
        except MechanicsActionError as error:
            raise TeachMunshiError(str(error)) from error

    if not isinstance(value, list) or not value or len(value) > 16:
        raise TeachMunshiError("Teach MUNSHI requires 1-16 bounded actions")
    normalized: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise TeachMunshiError("Teach MUNSHI actions must be objects")
        action_type = raw.get("type")
        if action_type in {"FOCUS", "CLICK", "SELECT_EXACT_OPTION"}:
            normalized.append({"type": str(action_type)})
            continue
        if action_type == "TYPE" and raw.get("valueSource") == "ANSWER":
            normalized.append({"type": "TYPE", "valueSource": "ANSWER"})
            continue
        if action_type == "KEY" and raw.get("key") in _ALLOWED_KEYS:
            normalized.append({"type": "KEY", "key": str(raw["key"])})
            continue
        if action_type == "WAIT_FOR_STATE" and raw.get("state") in _ALLOWED_WAIT_STATES:
            normalized.append(
                {"type": "WAIT_FOR_STATE", "state": str(raw["state"])}
            )
            continue
        raise TeachMunshiError(
            "Teach MUNSHI rejects unsupported or value-bearing actions"
        )
    return normalized

def _context(payload: dict[str, Any]) -> dict[str, str | None]:
    ats_family = _optional_text(payload.get("atsFamily"), "atsFamily", limit=80)
    return {
        "atsFamily": ats_family.upper() if ats_family else None,
        "tenantKey": _optional_text(payload.get("tenantKey"), "tenantKey"),
        "uiFingerprint": _optional_text(
            payload.get("uiFingerprint"), "uiFingerprint"
        ),
        "questionFingerprint": _optional_text(
            payload.get("questionFingerprint"), "questionFingerprint"
        ),
    }


def _canonical_actions(actions: list[dict[str, object]]) -> str:
    return json.dumps(actions, sort_keys=True, separators=(",", ":"))


def _same_actions(recipe: dict[str, object], actions: list[dict[str, object]]) -> bool:
    existing = recipe.get("actions")
    return isinstance(existing, list) and _canonical_actions(existing) == _canonical_actions(
        actions
    )


class TeachMunshiService:
    """Durable, non-blocking mechanics learning after a verified interaction.

    Capture performs only validation and a local SQLite insert. It never calls an AI
    provider. A worker drains lessons later, reusing the already-successful action
    trace to teach or reinforce a SHADOW recipe. This keeps learning off the browser
    critical path and avoids a second model call after a fallback already succeeded.
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        self.recipes = InteractionRecipeService(database)

    def capture(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise TeachMunshiError("Teach MUNSHI lesson payload must be an object")
        if payload.get("verifiedSuccess") is not True:
            raise TeachMunshiError(
                "Teach MUNSHI only captures already-verified successful interactions"
            )

        observation_id = _required_text(
            payload.get("observationId"), "observationId", limit=160
        )
        site_origin = _origin(payload.get("siteOrigin"))
        component_fingerprint = _required_text(
            payload.get("componentFingerprint"),
            "componentFingerprint",
            limit=240,
        )
        if not component_fingerprint.startswith("cfp-"):
            raise TeachMunshiError("componentFingerprint is invalid")
        semantic_type = _semantic(payload.get("semanticType"))
        actions = _actions(payload.get("actions"))
        context = _context(payload)

        teacher_kind = _required_text(
            payload.get("teacherKind"), "teacherKind", limit=40
        ).upper()
        if teacher_kind not in _TEACHER_KINDS:
            raise TeachMunshiError("teacherKind is not supported")
        provider = _optional_text(
            payload.get("teacherProvider"), "teacherProvider", limit=80
        )
        if teacher_kind in {"MODEL", "LOCAL_MODEL"} and provider is None:
            raise TeachMunshiError("Model-derived lessons require teacherProvider")
        source_lane = _required_text(
            payload.get("sourceLane"), "sourceLane", limit=80
        ).upper()
        application_id = _optional_text(
            payload.get("applicationId"), "applicationId", limit=240
        )

        canonical = {
            "observationId": observation_id,
            "applicationId": application_id,
            "siteOrigin": site_origin,
            "componentFingerprint": component_fingerprint,
            "semanticType": semantic_type,
            **context,
            "teacherKind": teacher_kind,
            "teacherProvider": provider.lower() if provider else None,
            "sourceLane": source_lane,
            "actions": actions,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        dedupe_key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        lesson_id = f"lesson-{dedupe_key[:32]}"
        now = datetime.now(UTC).isoformat()

        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO teach_munshi_lessons(
                    lesson_id, dedupe_key, application_id, site_origin,
                    component_fingerprint, semantic_type, ats_family, tenant_key,
                    ui_fingerprint, question_fingerprint, teacher_kind,
                    teacher_provider, source_lane, actions_json, state,
                    attempt_count, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',0,?,?)
                """,
                (
                    lesson_id,
                    dedupe_key,
                    application_id,
                    site_origin,
                    component_fingerprint,
                    semantic_type,
                    context["atsFamily"],
                    context["tenantKey"],
                    context["uiFingerprint"],
                    context["questionFingerprint"],
                    teacher_kind,
                    provider.lower() if provider else None,
                    source_lane,
                    _canonical_actions(actions),
                    now,
                    now,
                ),
            )
        return {
            "lessonId": lesson_id,
            "queued": True,
            "duplicate": result.rowcount == 0,
            "providerCallMade": False,
            "criticalPathWork": "LOCAL_SQLITE_INSERT_ONLY",
        }

    def recover_stale(
        self,
        *,
        stale_minutes: int = 10,
        at: str | None = None,
    ) -> dict[str, int]:
        if not 1 <= stale_minutes <= 1440:
            raise TeachMunshiError("stale_minutes must be between 1 and 1440")
        now = (
            datetime.fromisoformat(at.replace("Z", "+00:00"))
            if at
            else datetime.now(UTC)
        )
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        cutoff = (now.astimezone(UTC) - timedelta(minutes=stale_minutes)).isoformat()
        with self.database.connect() as connection:
            retry = connection.execute(
                """
                UPDATE teach_munshi_lessons
                SET state='PENDING', claimed_at=NULL,
                    failure_reason='recovered_stale_worker', updated_at=?
                WHERE state='PROCESSING' AND claimed_at < ?
                  AND attempt_count < ?
                """,
                (now.isoformat(), cutoff, _MAX_ATTEMPTS),
            ).rowcount
            failed = connection.execute(
                """
                UPDATE teach_munshi_lessons
                SET state='FAILED', completed_at=?,
                    failure_reason='worker_attempt_limit', updated_at=?
                WHERE state='PROCESSING' AND claimed_at < ?
                  AND attempt_count >= ?
                """,
                (now.isoformat(), now.isoformat(), cutoff, _MAX_ATTEMPTS),
            ).rowcount
        return {"requeued": retry, "failed": failed}

    def _claim(self) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM teach_munshi_lessons
                WHERE state='PENDING' AND attempt_count < ?
                ORDER BY created_at, lesson_id
                LIMIT 1
                """,
                (_MAX_ATTEMPTS,),
            ).fetchone()
            if row is None:
                return None
            changed = connection.execute(
                """
                UPDATE teach_munshi_lessons
                SET state='PROCESSING', attempt_count=attempt_count+1,
                    claimed_at=?, updated_at=?
                WHERE lesson_id=? AND state='PENDING'
                """,
                (now, now, row["lesson_id"]),
            ).rowcount
            if changed != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM teach_munshi_lessons WHERE lesson_id=?",
                (row["lesson_id"],),
            ).fetchone()
        return dict(claimed) if claimed is not None else None

    @staticmethod
    def _recipe_payload(row: dict[str, Any]) -> dict[str, object]:
        return {
            "applicationId": row["application_id"],
            "siteOrigin": row["site_origin"],
            "componentFingerprint": row["component_fingerprint"],
            "semanticType": row["semantic_type"],
            "atsFamily": row["ats_family"],
            "tenantKey": row["tenant_key"],
            "uiFingerprint": row["ui_fingerprint"],
            "questionFingerprint": row["question_fingerprint"],
        }

    def _learn(self, row: dict[str, Any]) -> dict[str, object]:
        actions = json.loads(row["actions_json"])
        if not isinstance(actions, list):
            raise TeachMunshiError("Stored lesson actions are invalid")
        payload = self._recipe_payload(row)
        existing = self.recipes.lookup(payload)
        attempt_id = f"teach-{row['lesson_id']}"
        if existing is not None and _same_actions(existing, actions):
            learned = self.recipes.record_outcome(
                {
                    "recipeId": existing["recipeId"],
                    "attemptId": attempt_id,
                    "applicationId": row["application_id"],
                    "success": True,
                    "verified": True,
                    "failureReason": None,
                }
            )
        else:
            learned = self.recipes.teach(
                {
                    **payload,
                    "attemptId": attempt_id,
                    "actions": actions,
                }
            )
        return learned

    def _complete(
        self,
        lesson_id: str,
        *,
        state: str,
        recipe_id: str | None,
        reason: str | None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE teach_munshi_lessons
                SET state=?, recipe_id=?, failure_reason=?,
                    completed_at=?, updated_at=?
                WHERE lesson_id=? AND state='PROCESSING'
                """,
                (state, recipe_id, reason, now, now, lesson_id),
            )

    def drain(self, *, limit: int = 20) -> dict[str, object]:
        if not 1 <= int(limit) <= 100:
            raise TeachMunshiError("Teach MUNSHI drain limit must be between 1 and 100")
        self.recover_stale()
        learned_count = 0
        failed_count = 0
        recipe_ids: list[str] = []
        for _ in range(int(limit)):
            row = self._claim()
            if row is None:
                break
            try:
                learned = self._learn(row)
                recipe_id = str(learned["recipeId"])
                self._complete(
                    str(row["lesson_id"]),
                    state="LEARNED",
                    recipe_id=recipe_id,
                    reason=None,
                )
                learned_count += 1
                recipe_ids.append(recipe_id)
            except (TeachMunshiError, ValueError) as error:
                self._complete(
                    str(row["lesson_id"]),
                    state="SKIPPED",
                    recipe_id=None,
                    reason=str(error)[:240],
                )
            except Exception as error:  # pragma: no cover - fail-safe worker boundary
                self._complete(
                    str(row["lesson_id"]),
                    state="FAILED",
                    recipe_id=None,
                    reason=type(error).__name__[:120],
                )
                failed_count += 1
        return {
            "learned": learned_count,
            "failed": failed_count,
            "recipeIds": recipe_ids,
            "providerCallMade": False,
        }

    def metrics(self) -> dict[str, object]:
        with self.database.connect() as connection:
            states = connection.execute(
                """
                SELECT state, COUNT(*) AS count
                FROM teach_munshi_lessons
                GROUP BY state
                ORDER BY state
                """
            ).fetchall()
            providers = connection.execute(
                """
                SELECT COALESCE(teacher_provider,'non-model') AS provider,
                       COUNT(*) AS count,
                       COALESCE(SUM(CASE WHEN state='LEARNED' THEN 1 ELSE 0 END),0)
                           AS learned
                FROM teach_munshi_lessons
                GROUP BY COALESCE(teacher_provider,'non-model')
                ORDER BY count DESC, provider
                """
            ).fetchall()
            totals = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN state='LEARNED' THEN 1 ELSE 0 END),0)
                           AS learned
                FROM teach_munshi_lessons
                """
            ).fetchone()
        total = int(totals["total"])
        learned = int(totals["learned"])
        return {
            "totalLessons": total,
            "learnedLessons": learned,
            "learningRate": round(learned / total, 6) if total else 0.0,
            "states": [dict(row) for row in states],
            "providers": [dict(row) for row in providers],
        }
