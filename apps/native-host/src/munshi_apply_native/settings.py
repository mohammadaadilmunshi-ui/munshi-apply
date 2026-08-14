from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    migrations_path: Path
    n8n_webhook_url: str | None
    n8n_webhook_secret: str | None
    log_level: str

    @classmethod
    def from_environment(cls) -> Settings:
        repository_root = Path(__file__).resolve().parents[4]
        database_path = Path(
            os.getenv("MUNSHI_DATABASE_PATH", repository_root / "data/munshi-apply.sqlite")
        ).expanduser()
        migrations_path = Path(
            os.getenv("MUNSHI_MIGRATIONS_PATH", repository_root / "migrations")
        ).expanduser()
        return cls(
            database_path=database_path,
            migrations_path=migrations_path,
            n8n_webhook_url=os.getenv("MUNSHI_N8N_WEBHOOK_URL") or None,
            n8n_webhook_secret=os.getenv("MUNSHI_N8N_WEBHOOK_SECRET") or None,
            log_level=os.getenv("MUNSHI_LOG_LEVEL", "INFO").upper(),
        )
