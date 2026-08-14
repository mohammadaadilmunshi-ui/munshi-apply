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
        return cls(
            runtime_root=runtime_root,
            database_path=database_path,
            migrations_path=migrations_path,
            n8n_webhook_url=n8n_webhook_url,
            n8n_webhook_secret=n8n_webhook_secret,
            outbox_poll_seconds=float(os.getenv("MUNSHI_OUTBOX_POLL_SECONDS", "5")),
            log_level=os.getenv("MUNSHI_LOG_LEVEL", "INFO").upper(),
        )

    @staticmethod
    def default_runtime_root() -> Path:
        if sys.platform == "darwin":
            return Path.home() / "Library/Application Support/MUNSHI Apply"
        if sys.platform == "win32":
            return Path(os.getenv("LOCALAPPDATA", Path.home())) / "MUNSHI Apply"
        return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / "MUNSHI Apply"
