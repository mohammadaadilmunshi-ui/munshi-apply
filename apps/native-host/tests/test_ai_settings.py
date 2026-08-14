from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import munshi_apply_native.ai_settings as ai_settings
from munshi_apply_native.ai_settings import AIConfiguration, AISettingsStore


def test_ai_settings_round_trip(tmp_path: Path) -> None:
    store = AISettingsStore(tmp_path)
    config = AIConfiguration.from_payload(
        {
            "provider": "openai",
            "enabled": True,
            "model": "gpt-test",
            "monthlyBudgetUsd": 25,
            "warningBudgetUsd": 20,
            "hardStop": True,
        }
    )
    store.save(config)
    loaded = store.load()
    assert loaded.enabled is True
    assert loaded.model == "gpt-test"
    assert loaded.monthly_budget_usd == 25
    assert loaded.warning_budget_usd == 20
    assert (tmp_path / "settings" / "ai.json").exists()
    assert not (tmp_path / "config" / "ai.json").exists()


def test_legacy_ai_settings_are_migrated_into_backed_up_settings(tmp_path: Path) -> None:
    legacy_path = tmp_path / "config" / "ai.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        json.dumps(
            {
                "provider": "openai",
                "enabled": False,
                "model": "gpt-legacy",
                "monthlyBudgetUsd": 12,
                "warningBudgetUsd": 8,
                "hardStop": True,
            }
        ),
        encoding="utf-8",
    )

    store = AISettingsStore(tmp_path)
    loaded = store.load()

    assert loaded.model == "gpt-legacy"
    assert loaded.monthly_budget_usd == 12
    assert (tmp_path / "settings" / "ai.json").exists()
    assert not legacy_path.exists()


def test_budget_validation_rejects_warning_above_budget() -> None:
    with pytest.raises(ValueError, match="Warning threshold"):
        AIConfiguration.from_payload(
            {
                "provider": "openai",
                "monthlyBudgetUsd": 5,
                "warningBudgetUsd": 10,
            }
        )


def test_environment_key_is_supported_as_headless_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = AISettingsStore(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-" + ("x" * 40))
    monkeypatch.setattr(store, "_keychain_read", lambda: None)
    assert store.key_source() == "environment"
    assert store.get_api_key().startswith("test-key-")


def test_status_never_returns_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AISettingsStore(tmp_path)
    sample_value = "test-key-" + ("y" * 40)
    monkeypatch.setenv("OPENAI_API_KEY", sample_value)
    monkeypatch.setattr(store, "_keychain_read", lambda: None)
    serialized = json.dumps(store.status())
    assert sample_value not in serialized
    assert '"keyConfigured": true' in serialized


def test_keychain_write_keeps_secret_out_of_process_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = AISettingsStore(tmp_path)
    sample_value = "sk-proj-test_" + ("z" * 40)
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> SimpleNamespace:
        captured["args"] = args
        captured.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ai_settings.sys, "platform", "darwin")
    monkeypatch.setattr(ai_settings.subprocess, "run", fake_run)

    store.set_api_key(sample_value)

    args = captured["args"]
    assert isinstance(args, list)
    assert args == ["/usr/bin/security", "-q", "-i"]
    assert sample_value not in " ".join(args)
    command = captured["input"]
    assert isinstance(command, str)
    assert sample_value not in command
    assert sample_value.encode("utf-8").hex() in command
    assert captured["text"] is True
