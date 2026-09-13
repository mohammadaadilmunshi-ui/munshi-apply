from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.settings import Settings


def test_runtime_root_controls_default_database_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.delenv("MUNSHI_DATABASE_PATH", raising=False)

    settings = Settings.from_environment()

    assert settings.runtime_root == tmp_path
    assert settings.database_path == tmp_path / "database/munshi-apply.sqlite"


def test_n8n_url_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUNSHI_N8N_WEBHOOK_URL", "https://example.test/hook")
    monkeypatch.delenv("MUNSHI_N8N_WEBHOOK_SECRET", raising=False)

    with pytest.raises(ValueError, match="MUNSHI_N8N_WEBHOOK_SECRET"):
        Settings.from_environment()


def test_teach_telegram_reuses_complete_legacy_hunter_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_bot_fixture = "existing-hunter-bot"  # noqa: S105 - synthetic test fixture
    monkeypatch.delenv("MUNSHI_TEACH_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("MUNSHI_TEACH_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", legacy_bot_fixture)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    settings = Settings.from_environment()

    assert settings.teach_telegram_bot_token == legacy_bot_fixture
    assert settings.teach_telegram_chat_id == "123456"


def test_partial_legacy_telegram_environment_does_not_break_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MUNSHI_TEACH_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("MUNSHI_TEACH_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "unpaired-legacy-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    settings = Settings.from_environment()

    assert settings.teach_telegram_bot_token is None
    assert settings.teach_telegram_chat_id is None


def test_partial_dedicated_teach_telegram_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUNSHI_TEACH_TELEGRAM_BOT_TOKEN", "dedicated-token")
    monkeypatch.delenv("MUNSHI_TEACH_TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(ValueError, match="both dedicated bot token and chat id"):
        Settings.from_environment()
