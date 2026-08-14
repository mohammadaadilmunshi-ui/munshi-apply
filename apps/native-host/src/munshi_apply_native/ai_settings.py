from __future__ import annotations

import json
import os
import subprocess  # noqa: S404
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

_KEYCHAIN_SERVICE = "systems.munshi.apply.openai"
_KEYCHAIN_ACCOUNT = "OPENAI_API_KEY"
_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"


@dataclass
class AIConfiguration:
    provider: str = "openai"
    enabled: bool = False
    model: str = ""
    monthly_budget_usd: float = 0.0
    warning_budget_usd: float = 0.0
    hard_stop: bool = True

    @classmethod
    def from_payload(cls, payload: object) -> AIConfiguration:
        if not isinstance(payload, dict):
            raise ValueError("AI settings payload must be an object")
        provider = str(payload.get("provider", "openai"))
        if provider != "openai":
            raise ValueError("Only the OpenAI provider is available in this release")
        monthly = float(payload.get("monthlyBudgetUsd", 0))
        warning = float(payload.get("warningBudgetUsd", 0))
        if monthly < 0 or warning < 0:
            raise ValueError("AI budget values cannot be negative")
        if monthly > 0 and warning > monthly:
            raise ValueError("Warning threshold cannot exceed the monthly budget")
        return cls(
            provider=provider,
            enabled=bool(payload.get("enabled", False)),
            model=str(payload.get("model", "")),
            monthly_budget_usd=monthly,
            warning_budget_usd=warning,
            hard_stop=bool(payload.get("hardStop", True)),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "model": self.model,
            "monthlyBudgetUsd": self.monthly_budget_usd,
            "warningBudgetUsd": self.warning_budget_usd,
            "hardStop": self.hard_stop,
        }


class AISettingsStore:
    def __init__(self, runtime_root: Path) -> None:
        self.config_path = runtime_root / "settings" / "ai.json"
        self.legacy_config_path = runtime_root / "config" / "ai.json"

    @staticmethod
    def _read_configuration(path: Path) -> AIConfiguration:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Local AI settings are unreadable") from error
        return AIConfiguration.from_payload(payload)

    def load(self) -> AIConfiguration:
        if self.config_path.exists():
            return self._read_configuration(self.config_path)
        if not self.legacy_config_path.exists():
            return AIConfiguration()

        config = self._read_configuration(self.legacy_config_path)
        self.save(config)
        try:
            self.legacy_config_path.unlink()
            self.legacy_config_path.parent.rmdir()
        except OSError:
            # Migration has already succeeded; leaving an old copy is safer than
            # failing configuration loading because another legacy file exists.
            pass
        return config

    def save(self, config: AIConfiguration) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {
            "provider": config.provider,
            "enabled": config.enabled,
            "model": config.model,
            "monthlyBudgetUsd": config.monthly_budget_usd,
            "warningBudgetUsd": config.warning_budget_usd,
            "hardStop": config.hard_stop,
        }
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.config_path.parent,
            prefix="ai-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        temporary.replace(self.config_path)
        os.chmod(self.config_path, 0o600)

    def _keychain_read(self) -> str | None:
        if sys.platform != "darwin":
            return None
        result = subprocess.run(  # noqa: S603
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-s",
                _KEYCHAIN_SERVICE,
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

    def key_source(self) -> str:
        if self._keychain_read():
            return "keychain"
        if os.getenv("OPENAI_API_KEY"):
            return "environment"
        return "none"

    def get_api_key(self) -> str:
        key = self._keychain_read() or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OpenAI API key is not configured")
        return key

    def set_api_key(self, api_key: object) -> None:
        if sys.platform != "darwin":
            raise ValueError("Secure desktop key entry currently requires macOS Keychain")
        if not isinstance(api_key, str) or len(api_key.strip()) < 20:
            raise ValueError("OpenAI API key is incomplete")
        cleaned_key = api_key.strip()
        password_hex = cleaned_key.encode("utf-8").hex()
        command = (
            f"add-generic-password -a {_KEYCHAIN_ACCOUNT} "
            f"-s {_KEYCHAIN_SERVICE} -U -X {password_hex}\n"
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
            raise ValueError("macOS Keychain rejected the OpenAI credential")

    def delete_api_key(self) -> None:
        if sys.platform != "darwin":
            return
        subprocess.run(  # noqa: S603
            [
                "/usr/bin/security",
                "delete-generic-password",
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-s",
                _KEYCHAIN_SERVICE,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def status(self) -> dict[str, object]:
        config = self.load()
        source = self.key_source()
        return {
            **config.public_dict(),
            "keyConfigured": source != "none",
            "keySource": source,
        }

    def _openai_request(self, url: str) -> dict[str, Any]:
        if url != _OPENAI_MODELS_URL:
            raise ValueError("Unapproved OpenAI endpoint")
        request = urllib_request.Request(  # noqa: S310
            url,
            headers={
                "Authorization": f"Bearer {self.get_api_key()}",
                "Accept": "application/json",
                "User-Agent": "MUNSHI-Apply/0.2",
            },
        )
        try:
            with urllib_request.urlopen(request, timeout=10) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as error:
            raise ValueError(f"OpenAI connection failed (HTTP {error.code})") from error
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ValueError("OpenAI connection failed") from error
        if not isinstance(payload, dict):
            raise ValueError("OpenAI returned an invalid response")
        return payload

    def list_models(self) -> list[str]:
        payload = self._openai_request(_OPENAI_MODELS_URL)
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("OpenAI model list is unavailable")
        model_ids = [
            item.get("id")
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        preferred = [
            model_id
            for model_id in model_ids
            if model_id.startswith(("gpt-", "o1", "o3", "o4"))
            and "audio" not in model_id
            and "realtime" not in model_id
            and "transcribe" not in model_id
            and "tts" not in model_id.lower()
            and "image" not in model_id
        ]
        return sorted(set(preferred))
