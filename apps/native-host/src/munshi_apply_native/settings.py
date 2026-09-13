from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    runtime_root: Path
    database_path: Path
    migrations_path: Path
    n8n_webhook_url: str | None
    n8n_webhook_secret: str | None
    outbox_poll_seconds: float
    log_level: str
    command_secret: str | None = None
    handoff_hmac_secret: str | None = None
    teach_telegram_bot_token: str | None = None
    teach_telegram_chat_id: str | None = None
    teach_telegram_poll_seconds: float = 15.0

    @classmethod
    def from_environment(cls) -> Settings:
        repository_root = Path(__file__).resolve().parents[4]
        runtime_root = Path(
            os.getenv("MUNSHI_RUNTIME_ROOT", cls.default_runtime_root())
        ).expanduser()
        database_path = Path(
            os.getenv("MUNSHI_DATABASE_PATH", runtime_root / "database/munshi-apply.sqlite")
        ).expanduser()
        migrations_path = Path(
            os.getenv("MUNSHI_MIGRATIONS_PATH", repository_root / "migrations")
        ).expanduser()
        n8n_webhook_url = os.getenv("MUNSHI_N8N_WEBHOOK_URL") or None
        n8n_webhook_secret = os.getenv("MUNSHI_N8N_WEBHOOK_SECRET") or None
        if n8n_webhook_url and not n8n_webhook_secret:
            raise ValueError("MUNSHI_N8N_WEBHOOK_SECRET is required when n8n is configured")

        # Dedicated names are authoritative when configured. Legacy TELEGRAM_*
        # values are adopted only when the complete existing Hunter pair is
        # present, so an unrelated partial legacy environment cannot break Apply.
        dedicated_token = os.getenv("MUNSHI_TEACH_TELEGRAM_BOT_TOKEN") or None
        dedicated_chat = os.getenv("MUNSHI_TEACH_TELEGRAM_CHAT_ID") or None
        if bool(dedicated_token) != bool(dedicated_chat):
            raise ValueError(
                "Teach MUNSHI Telegram requires both dedicated bot token and chat id"
            )
        if dedicated_token and dedicated_chat:
            teach_telegram_bot_token = dedicated_token
            teach_telegram_chat_id = dedicated_chat
        else:
            legacy_token = os.getenv("TELEGRAM_BOT_TOKEN") or None
            legacy_chat = os.getenv("TELEGRAM_CHAT_ID") or None
            if legacy_token and legacy_chat:
                teach_telegram_bot_token = legacy_token
                teach_telegram_chat_id = legacy_chat
            else:
                teach_telegram_bot_token = None
                teach_telegram_chat_id = None

        teach_telegram_poll_seconds = float(
            os.getenv("MUNSHI_TEACH_TELEGRAM_POLL_SECONDS", "15")
        )
        if teach_telegram_poll_seconds <= 0:
            raise ValueError("MUNSHI_TEACH_TELEGRAM_POLL_SECONDS must be positive")

        return cls(
            runtime_root=runtime_root,
            database_path=database_path,
            migrations_path=migrations_path,
            n8n_webhook_url=n8n_webhook_url,
            n8n_webhook_secret=n8n_webhook_secret,
            outbox_poll_seconds=float(os.getenv("MUNSHI_OUTBOX_POLL_SECONDS", "5")),
            log_level=os.getenv("MUNSHI_LOG_LEVEL", "INFO").upper(),
            command_secret=os.getenv("MUNSHI_APPLY_COMMAND_SECRET") or None,
            handoff_hmac_secret=os.getenv("MUNSHI_APPLY_HANDOFF_HMAC_SECRET") or None,
            teach_telegram_bot_token=teach_telegram_bot_token,
            teach_telegram_chat_id=teach_telegram_chat_id,
            teach_telegram_poll_seconds=teach_telegram_poll_seconds,
        )

    @staticmethod
    def default_runtime_root() -> Path:
        if sys.platform == "darwin":
            return Path.home() / "Library/Application Support/MUNSHI Apply"
        if sys.platform == "win32":
            return Path(os.getenv("LOCALAPPDATA", Path.home())) / "MUNSHI Apply"
        return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / "MUNSHI Apply"
