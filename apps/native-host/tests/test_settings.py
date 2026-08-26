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
