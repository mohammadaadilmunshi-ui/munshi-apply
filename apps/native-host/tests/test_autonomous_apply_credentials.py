from __future__ import annotations

import json
from pathlib import Path

import pytest

from munshi_apply_native.autonomous_apply_credentials import (
    AutonomousApplyConfiguration,
    AutonomousApplyCredentialStore,
)


def test_configuration_round_trip(tmp_path: Path) -> None:
    store = AutonomousApplyCredentialStore(tmp_path)
    config = AutonomousApplyConfiguration.from_payload(
        {
            "enabled": True,
            "authMode": "subscription",
            "model": "sonnet",
            "headless": True,
            "maxTurns": 25,
            "maxCostPerApplicationUsd": 0.5,
            "allowFinalSubmit": False,
            "challengeServiceEnabled": False,
        }
    )

    store.save(config)
    loaded = store.load()

    assert loaded == config
    persisted = json.loads(store.config_path.read_text(encoding="utf-8"))
    assert persisted["authMode"] == "subscription"
    assert "apiKey" not in persisted
    assert "ANTHROPIC_API_KEY" not in persisted
    assert "CAPSOLVER_API_KEY" not in persisted


def test_environment_credentials_are_reported_without_exposure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-secret-value")
    monkeypatch.setenv("CAPSOLVER_API_KEY", "test-capsolver-secret-value")
    store = AutonomousApplyCredentialStore(tmp_path)

    status = store.status()

    assert status["anthropicKeyConfigured"] is True
    assert status["anthropicKeySource"] == "environment"
    assert status["capSolverKeyConfigured"] is True
    assert status["capSolverKeySource"] == "environment"
    serialized = json.dumps(status)
    assert "test-anthropic-secret-value" not in serialized
    assert "test-capsolver-secret-value" not in serialized


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"authMode": "unknown"}, "authMode"),
        ({"maxTurns": 0}, "maxTurns"),
        ({"maxTurns": 201}, "maxTurns"),
        ({"maxCostPerApplicationUsd": -1}, "maxCostPerApplicationUsd"),
    ],
)
def test_invalid_configuration_rejected(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AutonomousApplyConfiguration.from_payload(payload)


def test_runtime_status_requires_cli_and_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = AutonomousApplyCredentialStore(tmp_path)
    store.save(
        AutonomousApplyConfiguration(
            enabled=True,
            auth_mode="api",
            model="sonnet",
        )
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-secret-value")

    def fake_which(name: str) -> str | None:
        return f"/usr/local/bin/{name}" if name in {"claude", "npx"} else None

    monkeypatch.setattr(
        "munshi_apply_native.autonomous_apply_credentials.shutil.which", fake_which
    )

    status = store.runtime_status()

    assert status["claudeCliInstalled"] is True
    assert status["playwrightLauncherInstalled"] is True
    assert status["credentialReady"] is True
    assert status["readyForDryRun"] is True


def test_subscription_mode_does_not_require_stored_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store = AutonomousApplyCredentialStore(tmp_path)
    store.save(AutonomousApplyConfiguration(auth_mode="subscription"))
    monkeypatch.setattr(
        "munshi_apply_native.autonomous_apply_credentials.shutil.which",
        lambda name: f"/usr/local/bin/{name}",
    )

    status = store.runtime_status()

    assert status["credentialReady"] is True
    assert status["readyForDryRun"] is True
