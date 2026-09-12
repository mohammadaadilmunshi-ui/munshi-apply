from __future__ import annotations

import json
import os
import shutil
import subprocess  # noqa: S404
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_ALLOWED_AUTH_MODES = {"subscription", "api"}
_KEYCHAIN_SERVICE_PREFIX = "systems.munshi.apply.autonomous"
_SECRET_DEFINITIONS = {
    "anthropic": ("ANTHROPIC_API_KEY", f"{_KEYCHAIN_SERVICE_PREFIX}.anthropic"),
    "capsolver": ("CAPSOLVER_API_KEY", f"{_KEYCHAIN_SERVICE_PREFIX}.capsolver"),
}


@dataclass
class AutonomousApplyConfiguration:
    enabled: bool = False
    auth_mode: str = "subscription"
    model: str = "sonnet"
    headless: bool = False
    max_turns: int = 40
    max_cost_per_application_usd: float = 1.0
    allow_final_submit: bool = False
    challenge_service_enabled: bool = False

    @classmethod
    def from_payload(cls, payload: object) -> AutonomousApplyConfiguration:
        if not isinstance(payload, dict):
            raise ValueError("Autonomous apply settings payload must be an object")
        auth_mode = str(payload.get("authMode", "subscription")).strip().lower()
        if auth_mode not in _ALLOWED_AUTH_MODES:
            raise ValueError("Autonomous apply authMode must be subscription or api")
        model = str(payload.get("model", "sonnet")).strip()
        if not model or len(model) > 120:
            raise ValueError("Autonomous apply model is invalid")
        max_turns = int(payload.get("maxTurns", 40))
        if max_turns < 1 or max_turns > 200:
            raise ValueError("Autonomous apply maxTurns must be between 1 and 200")
        max_cost = float(payload.get("maxCostPerApplicationUsd", 1.0))
        if max_cost < 0 or max_cost > 100:
            raise ValueError(
                "Autonomous apply maxCostPerApplicationUsd must be between 0 and 100"
            )
        return cls(
            enabled=bool(payload.get("enabled", False)),
            auth_mode=auth_mode,
            model=model,
            headless=bool(payload.get("headless", False)),
            max_turns=max_turns,
            max_cost_per_application_usd=max_cost,
            allow_final_submit=bool(payload.get("allowFinalSubmit", False)),
            challenge_service_enabled=bool(payload.get("challengeServiceEnabled", False)),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "authMode": self.auth_mode,
            "model": self.model,
            "headless": self.headless,
            "maxTurns": self.max_turns,
            "maxCostPerApplicationUsd": self.max_cost_per_application_usd,
            "allowFinalSubmit": self.allow_final_submit,
            "challengeServiceEnabled": self.challenge_service_enabled,
        }


class AutonomousApplyCredentialStore:
    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root
        self.config_path = runtime_root / "settings" / "autonomous-apply.json"

    def load(self) -> AutonomousApplyConfiguration:
        if not self.config_path.exists():
            return AutonomousApplyConfiguration()
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Autonomous apply settings are unreadable") from error
        return AutonomousApplyConfiguration.from_payload(payload)

    def save(self, config: AutonomousApplyConfiguration) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.config_path.parent,
            prefix="autonomous-apply-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(config.public_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        temporary.replace(self.config_path)
        os.chmod(self.config_path, 0o600)

    @staticmethod
    def _definition(secret_name: str) -> tuple[str, str]:
        definition = _SECRET_DEFINITIONS.get(secret_name)
        if definition is None:
            raise ValueError("Unsupported autonomous apply credential")
        return definition

    def _keychain_read(self, secret_name: str) -> str | None:
        if sys.platform != "darwin":
            return None
        account, service = self._definition(secret_name)
        result = subprocess.run(  # noqa: S603
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                account,
                "-s",
                service,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def secret_source(self, secret_name: str) -> str:
        account, _service = self._definition(secret_name)
        if self._keychain_read(secret_name):
            return "keychain"
        if os.getenv(account):
            return "environment"
        return "none"

    def get_secret(self, secret_name: str) -> str:
        account, _service = self._definition(secret_name)
        value = self._keychain_read(secret_name) or os.getenv(account)
        if not value:
            raise ValueError(f"{account} is not configured")
        return value

    def set_secret(self, secret_name: str, value: object) -> None:
        if sys.platform != "darwin":
            raise ValueError("Secure credential entry currently requires macOS Keychain")
        account, service = self._definition(secret_name)
        if not isinstance(value, str) or len(value.strip()) < 12:
            raise ValueError(f"{account} is incomplete")
        cleaned = value.strip()
        password_hex = cleaned.encode("utf-8").hex()
        command = (
            f"add-generic-password -a {account} -s {service} -U -X {password_hex}\n"
        )
        result = subprocess.run(  # noqa: S603
            ["/usr/bin/security", "-q", "-i"],
            check=False,
            input=command,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise ValueError(f"macOS Keychain rejected {account}")

    def delete_secret(self, secret_name: str) -> None:
        if sys.platform != "darwin":
            return
        account, service = self._definition(secret_name)
        subprocess.run(  # noqa: S603
            [
                "/usr/bin/security",
                "delete-generic-password",
                "-a",
                account,
                "-s",
                service,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def status(self) -> dict[str, object]:
        config = self.load()
        anthropic_source = self.secret_source("anthropic")
        capsolver_source = self.secret_source("capsolver")
        return {
            **config.public_dict(),
            "anthropicKeyConfigured": anthropic_source != "none",
            "anthropicKeySource": anthropic_source,
            "capSolverKeyConfigured": capsolver_source != "none",
            "capSolverKeySource": capsolver_source,
        }

    def runtime_status(self) -> dict[str, object]:
        config = self.load()
        claude_path = shutil.which("claude")
        npx_path = shutil.which("npx")
        api_ready = self.secret_source("anthropic") != "none"
        return {
            **self.status(),
            "claudeCliInstalled": claude_path is not None,
            "claudeCliPath": claude_path,
            "playwrightLauncherInstalled": npx_path is not None,
            "npxPath": npx_path,
            "credentialReady": config.auth_mode == "subscription" or api_ready,
            "readyForDryRun": claude_path is not None
            and npx_path is not None
            and (config.auth_mode == "subscription" or api_ready),
        }
