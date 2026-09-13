from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .database import Database

_BACKOFF_SECONDS = (10, 30, 120, 600, 1800)
_ALLOWED_EVENT_TYPES = {
    "RECIPE_PROMOTED",
    "RECIPE_ROLLED_BACK",
    "LEARNING_FAILED",
}
_ACTIVATION_KEY = "teach_munshi_telegram_activated_at"


@dataclass(frozen=True)
class TelegramTeachDeliverySummary:
    discovered: int = 0
    claimed: int = 0
    delivered: int = 0
    retry: int = 0
    dead_letter: int = 0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_text(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    if not clean:
        return None
    return clean[:limit]


def _event_id(event_type: str, identity: str) -> str:
    material = f"teach-munshi-telegram-v1\n{event_type}\n{identity}"
    return f"teach-tg-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


def _telegram_send(
    bot_token: str,
    chat_id: str,
    text: str,
    timeout_seconds: float,
) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        response = httpx.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as error:
        # Never persist an exception string that could contain the bot-token URL.
        raise RuntimeError(f"telegram_transport_{type(error).__name__}") from None
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"telegram_http_{response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("telegram_invalid_json") from None
    if payload.get("ok") is not True:
        raise RuntimeError("telegram_api_rejected")


def _format_message(event: dict[str, Any]) -> str:
    event_type = str(event.get("eventType") or "")
    ats_family = _safe_text(event.get("atsFamily"), limit=80) or "Unknown / custom ATS"
    recipe_id = _safe_text(event.get("recipeId"), limit=80)
    recipe_label = recipe_id[-10:] if recipe_id else "unknown"
    version = int(event.get("version") or 0)
    successes = int(event.get("verifiedSuccesses") or 0)
    failures = int(event.get("verifiedFailures") or 0)

    if event_type == "RECIPE_PROMOTED":
        title = "🧠 <b>Teach MUNSHI promoted a lesson</b>"
        state_line = "State: <b>SHADOW → PROMOTED</b>"
        outcome = "Future matching controls can use deterministic handling before AI."
    elif event_type == "RECIPE_ROLLED_BACK":
        title = "⚠️ <b>Teach MUNSHI rolled back a lesson</b>"
        state_line = "State: <b>PROMOTED → ROLLED BACK</b>"
        outcome = "The learned path is disabled and normal fallback handling is restored."
    elif event_type == "LEARNING_FAILED":
        title = "❌ <b>Teach MUNSHI learning needs attention</b>"
        state_line = "State: <b>learning failed</b>"
        outcome = "Application execution remains independent; this learning item was not trusted."
    else:
        raise ValueError("Unsupported Teach MUNSHI Telegram event")

    lines = [
        title,
        f"ATS: <b>{html.escape(ats_family)}</b>",
        state_line,
    ]
    if event_type != "LEARNING_FAILED":
        lines.extend(
            [
                f"Verified: <b>{successes} success / {failures} failure</b>",
                f"Recipe: <code>{html.escape(recipe_label)}</code> · v{version}",
            ]
        )
    else:
        provider = _safe_text(event.get("teacherProvider"), limit=80)
        source_lane = _safe_text(event.get("sourceLane"), limit=80)
        if provider:
            lines.append(f"Teacher: <b>{html.escape(provider)}</b>")
        if source_lane:
            lines.append(f"Lane: <b>{html.escape(source_lane)}</b>")
    lines.extend([outcome, "🔒 Candidate answer values are not included in this update."])
    return "\n".join(lines)


class TeachMunshiTelegramWorker:
    """Best-effort Telegram telemetry for meaningful Teach MUNSHI events.

    This worker reads only recipe/lesson metadata from the local Apply database.
    It never reads Candidate Truth values, application answers, credentials, OTPs,
    passwords, or captured typed values. Delivery is asynchronous and therefore
    cannot block browser filling or recipe learning.
    """

    def __init__(
        self,
        database: Database,
        bot_token: str,
        chat_id: str,
        *,
        sender: Callable[[str, str, str, float], None] = _telegram_send,
        max_attempts: int = len(_BACKOFF_SECONDS) + 1,
        activation_at: str | None = None,
    ) -> None:
        if not bot_token.strip() or not chat_id.strip():
            raise ValueError("Teach MUNSHI Telegram requires bot token and chat id")
        self.database = database
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.sender = sender
        self.max_attempts = max_attempts
        self.ensure_schema(activation_at=activation_at)

    def ensure_schema(self, *, activation_at: str | None = None) -> None:
        activated = activation_at or _utc_now()
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS teach_munshi_telegram_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS teach_munshi_telegram_outbox (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    delivery_state TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK(delivery_state IN (
                            'PENDING','DELIVERING','DELIVERED','DEAD_LETTER'
                        )),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivered_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_teach_munshi_tg_due
                ON teach_munshi_telegram_outbox(
                    delivery_state, next_attempt_at, created_at
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO teach_munshi_telegram_meta(
                    key, value, created_at, updated_at
                ) VALUES(?,?,?,?)
                """,
                (_ACTIVATION_KEY, activated, activated, activated),
            )

    def _activation_at(self) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM teach_munshi_telegram_meta WHERE key=?",
                (_ACTIVATION_KEY,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Teach MUNSHI Telegram activation watermark is missing")
        return str(row["value"])

    def _enqueue(self, event: dict[str, Any], identity: str) -> bool:
        event_type = str(event.get("eventType") or "")
        if event_type not in _ALLOWED_EVENT_TYPES:
            raise ValueError("Teach MUNSHI Telegram event type is not allowed")
        # Explicit metadata allowlist. Unknown keys, including answer/value fields,
        # are dropped before anything is persisted or delivered to Telegram.
        safe_event = {
            key: event.get(key)
            for key in (
                "eventType",
                "occurredAt",
                "recipeId",
                "version",
                "state",
                "verifiedSuccesses",
                "verifiedFailures",
                "atsFamily",
                "lessonId",
                "teacherKind",
                "teacherProvider",
                "sourceLane",
            )
        }
        now = _utc_now()
        event_id = _event_id(event_type, identity)
        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO teach_munshi_telegram_outbox(
                    event_id, event_type, payload_json, delivery_state,
                    attempt_count, next_attempt_at, created_at, updated_at
                ) VALUES(?,?,?,'PENDING',0,NULL,?,?)
                """,
                (
                    event_id,
                    event_type,
                    json.dumps(safe_event, sort_keys=True, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        return result.rowcount == 1

    def discover_events(self) -> int:
        discovered = 0
        activated_at = self._activation_at()
        with self.database.connect() as connection:
            recipes = connection.execute(
                """
                SELECT r.recipe_id, r.state, r.version, r.updated_at,
                       COALESCE(c.ats_family, '') AS ats_family,
                       SUM(CASE WHEN a.verified=1 AND a.success=1 THEN 1 ELSE 0 END)
                           AS verified_successes,
                       SUM(CASE WHEN a.verified=1 AND a.success=0 THEN 1 ELSE 0 END)
                           AS verified_failures
                FROM interaction_recipes r
                LEFT JOIN interaction_recipe_context c ON c.recipe_id=r.recipe_id
                LEFT JOIN recipe_attempts a ON a.recipe_id=r.recipe_id
                WHERE r.state IN ('PROMOTED','ROLLED_BACK')
                  AND r.updated_at >= ?
                GROUP BY r.recipe_id, r.state, r.version, r.updated_at, c.ats_family
                """,
                (activated_at,),
            ).fetchall()
            lesson_table = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='teach_munshi_lessons'
                """
            ).fetchone()
            failed_lessons = (
                connection.execute(
                    """
                    SELECT lesson_id, ats_family, teacher_kind, teacher_provider,
                           source_lane, updated_at
                    FROM teach_munshi_lessons
                    WHERE state='FAILED' AND updated_at >= ?
                    """,
                    (activated_at,),
                ).fetchall()
                if lesson_table is not None
                else []
            )

        for row in recipes:
            state = str(row["state"])
            event_type = (
                "RECIPE_PROMOTED" if state == "PROMOTED" else "RECIPE_ROLLED_BACK"
            )
            identity = (
                f"{row['recipe_id']}|{state}|{row['version']}|{row['updated_at']}"
            )
            discovered += int(
                self._enqueue(
                    {
                        "eventType": event_type,
                        "occurredAt": row["updated_at"],
                        "recipeId": row["recipe_id"],
                        "version": row["version"],
                        "state": state,
                        "verifiedSuccesses": int(row["verified_successes"] or 0),
                        "verifiedFailures": int(row["verified_failures"] or 0),
                        "atsFamily": row["ats_family"] or None,
                    },
                    identity,
                )
            )

        for row in failed_lessons:
            identity = f"lesson|{row['lesson_id']}|FAILED|{row['updated_at']}"
            discovered += int(
                self._enqueue(
                    {
                        "eventType": "LEARNING_FAILED",
                        "occurredAt": row["updated_at"],
                        "lessonId": row["lesson_id"],
                        "atsFamily": row["ats_family"],
                        "teacherKind": row["teacher_kind"],
                        "teacherProvider": row["teacher_provider"],
                        "sourceLane": row["source_lane"],
                    },
                    identity,
                )
            )
        return discovered

    def _recover_stale(self, clock: datetime) -> None:
        cutoff = (clock - timedelta(minutes=5)).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE teach_munshi_telegram_outbox
                SET delivery_state='PENDING', updated_at=?
                WHERE delivery_state='DELIVERING' AND updated_at < ?
                """,
                (clock.isoformat(), cutoff),
            )

    def _claim_due(self, clock: datetime, limit: int) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT * FROM teach_munshi_telegram_outbox
                WHERE delivery_state='PENDING'
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (clock.isoformat(), limit),
            ).fetchall()
            for row in rows:
                changed = connection.execute(
                    """
                    UPDATE teach_munshi_telegram_outbox
                    SET delivery_state='DELIVERING', attempt_count=attempt_count+1,
                        updated_at=?
                    WHERE event_id=? AND delivery_state='PENDING'
                    """,
                    (clock.isoformat(), row["event_id"]),
                ).rowcount
                if changed == 1:
                    claimed.append(dict(row))
        return claimed

    def deliver_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 20,
    ) -> TelegramTeachDeliverySummary:
        clock = now or datetime.now(UTC)
        discovered = self.discover_events()
        self._recover_stale(clock)
        claimed = self._claim_due(clock, limit)
        delivered = retry = dead_letter = 0

        for row in claimed:
            try:
                event = json.loads(str(row["payload_json"]))
                if not isinstance(event, dict):
                    raise ValueError("Teach MUNSHI Telegram payload is invalid")
                self.sender(
                    self.bot_token,
                    self.chat_id,
                    _format_message(event),
                    3.0,
                )
                with self.database.connect() as connection:
                    connection.execute(
                        """
                        UPDATE teach_munshi_telegram_outbox
                        SET delivery_state='DELIVERED', delivered_at=?,
                            updated_at=?, last_error=NULL
                        WHERE event_id=?
                        """,
                        (clock.isoformat(), clock.isoformat(), row["event_id"]),
                    )
                delivered += 1
            except Exception as error:
                attempt = int(row["attempt_count"]) + 1
                if attempt >= self.max_attempts:
                    state = "DEAD_LETTER"
                    next_attempt_at = None
                    dead_letter += 1
                else:
                    state = "PENDING"
                    delay_index = min(max(attempt - 1, 0), len(_BACKOFF_SECONDS) - 1)
                    next_attempt_at = (
                        clock + timedelta(seconds=_BACKOFF_SECONDS[delay_index])
                    ).isoformat()
                    retry += 1
                safe_error = type(error).__name__[:80]
                if isinstance(error, RuntimeError):
                    safe_error = str(error)[:120]
                with self.database.connect() as connection:
                    connection.execute(
                        """
                        UPDATE teach_munshi_telegram_outbox
                        SET delivery_state=?, next_attempt_at=?, last_error=?, updated_at=?
                        WHERE event_id=?
                        """,
                        (
                            state,
                            next_attempt_at,
                            safe_error,
                            clock.isoformat(),
                            row["event_id"],
                        ),
                    )

        return TelegramTeachDeliverySummary(
            discovered=discovered,
            claimed=len(claimed),
            delivered=delivered,
            retry=retry,
            dead_letter=dead_letter,
        )


async def run_teach_munshi_telegram_worker(
    worker: TeachMunshiTelegramWorker,
    stop_event: Any,
    *,
    poll_seconds: float,
) -> None:
    import asyncio

    while not stop_event.is_set():
        await asyncio.to_thread(worker.deliver_due)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            continue
