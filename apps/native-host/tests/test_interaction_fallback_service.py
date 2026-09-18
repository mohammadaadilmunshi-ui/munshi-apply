from __future__ import annotations

import json
from pathlib import Path

import pytest

from munshi_apply_native import interaction_fallback_service as fallback_module

from munshi_apply_native.autonomous_apply_credentials import (
    AutonomousApplyConfiguration,
    AutonomousApplyCredentialStore,
)
from munshi_apply_native.interaction_fallback_service import (
    InteractionFallbackError,
    InteractionFallbackService,
)


def configured_service(tmp_path: Path, output: dict[str, object]):
    store = AutonomousApplyCredentialStore(tmp_path)
    store.save(
        AutonomousApplyConfiguration(
            enabled=True,
            auth_mode="subscription",
            model="sonnet",
            max_turns=40,
            max_cost_per_application_usd=1.0,
            allow_final_submit=False,
        )
    )
    calls: list[dict[str, object]] = []

    def runner(
        prompt: str,
        model: str,
        auth_mode: str,
        max_cost_usd: float,
        max_wall_seconds: int,
        api_key: str | None,
    ) -> str:
        calls.append(
            {
                "prompt": prompt,
                "model": model,
                "auth_mode": auth_mode,
                "max_cost_usd": max_cost_usd,
                "max_wall_seconds": max_wall_seconds,
                "api_key": api_key,
            }
        )
        result = "MUNSHI_INTERACTION_RECOVERY=" + json.dumps(output)
        return json.dumps({"type": "result", "result": result})

    return InteractionFallbackService(tmp_path, runner=runner), calls


def safe_payload() -> dict[str, object]:
    return {
        "siteOrigin": "https://jobs.example.com",
        "componentFingerprint": "cfp-example-123",
        "semanticType": "CURRENT_LOCATION",
        "controlKind": "COMBOBOX",
        "label": "State",
        "role": "combobox",
        "hasPopup": "listbox",
        "atsFamily": "GENERIC",
        "options": ["New Jersey", "Pennsylvania"],
        "failureReason": "ordinary combobox path did not verify",
        "reversible": True,
        "sensitive": False,
        "authenticationBoundary": False,
        "finalSubmit": False,
    }


def test_proposal_is_value_free_and_bounded(tmp_path: Path) -> None:
    service, calls = configured_service(
        tmp_path,
        {
            "actions": [
                {"type": "FOCUS"},
                {"type": "CLICK"},
                {"type": "TYPE", "valueSource": "ANSWER"},
                {"type": "KEY", "key": "ArrowDown"},
                {"type": "KEY", "key": "Enter"},
                {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
            ],
            "reason": "Use the keyboard-operated combobox pattern",
        },
    )

    proposal = service.propose(safe_payload())

    assert proposal["provider"] == "claude"
    assert proposal["sourceLane"] == "AUTOAPPLY_FALLBACK"
    assert proposal["providerCallMade"] is True
    assert proposal["valueBearingInputSent"] is False
    assert proposal["actions"][2] == {"type": "TYPE", "valueSource": "ANSWER"}
    assert len(calls) == 1
    prompt = str(calls[0]["prompt"])
    assert "candidate's answer" in prompt
    assert "New Jersey" in prompt  # employer option text is permitted context
    assert calls[0]["max_cost_usd"] == 0.15
    assert calls[0]["api_key"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sensitive", True),
        ("reversible", False),
        ("authenticationBoundary", True),
        ("finalSubmit", True),
    ],
)
def test_security_boundaries_block_before_provider_call(
    tmp_path: Path, field: str, value: bool
) -> None:
    service, calls = configured_service(
        tmp_path, {"actions": [{"type": "CLICK"}], "reason": "unused"}
    )
    payload = safe_payload()
    payload[field] = value

    with pytest.raises(InteractionFallbackError):
        service.propose(payload)

    assert calls == []


@pytest.mark.parametrize(
    "semantic_type",
    ["CAPTCHA", "OTP", "MFA", "AUTHENTICATION", "GOVERNMENT_ID", "FINAL_SUBMIT"],
)
def test_security_semantics_never_reach_provider(
    tmp_path: Path, semantic_type: str
) -> None:
    service, calls = configured_service(
        tmp_path, {"actions": [{"type": "CLICK"}], "reason": "unused"}
    )
    payload = safe_payload()
    payload["semanticType"] = semantic_type

    with pytest.raises(InteractionFallbackError, match="Security controls"):
        service.propose(payload)

    assert calls == []


def test_value_bearing_model_action_is_rejected(tmp_path: Path) -> None:
    service, calls = configured_service(
        tmp_path,
        {
            "actions": [{"type": "TYPE", "value": "candidate-secret"}],
            "reason": "unsafe",
        },
    )

    with pytest.raises(InteractionFallbackError, match="value-bearing"):
        service.propose(safe_payload())

    assert len(calls) == 1


def test_disabled_fallback_does_not_call_provider(tmp_path: Path) -> None:
    AutonomousApplyCredentialStore(tmp_path).save(
        AutonomousApplyConfiguration(enabled=False, model="sonnet")
    )
    calls: list[str] = []

    def runner(*args):  # pragma: no cover - must not run
        calls.append("called")
        return ""

    service = InteractionFallbackService(tmp_path, runner=runner)
    with pytest.raises(InteractionFallbackError, match="disabled"):
        service.propose(safe_payload())
    assert calls == []


def test_hosted_api_mode_uses_dashboard_config_and_secret_resolvers(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    secret_calls: list[str] = []

    def runner(
        prompt: str,
        model: str,
        auth_mode: str,
        max_cost_usd: float,
        max_wall_seconds: int,
        api_key: str | None,
    ) -> str:
        calls.append(
            {
                "prompt": prompt,
                "model": model,
                "auth_mode": auth_mode,
                "max_cost_usd": max_cost_usd,
                "max_wall_seconds": max_wall_seconds,
                "api_key": api_key,
            }
        )
        result = "MUNSHI_INTERACTION_RECOVERY=" + json.dumps(
            {"actions": [{"type": "CLICK"}], "reason": "bounded"}
        )
        return json.dumps({"type": "result", "result": result})

    service = InteractionFallbackService(
        tmp_path,
        runner=runner,
        config_resolver=lambda: {
            "enabled": True,
            "authMode": "api",
            "model": "sonnet",
            "headless": True,
            "maxTurns": 40,
            "maxCostPerApplicationUsd": 1.0,
            "allowFinalSubmit": False,
            "challengeServiceEnabled": False,
        },
        api_key_resolver=lambda: secret_calls.append("called") or "dashboard-anthropic-secret",
    )

    proposal = service.propose(safe_payload())

    assert proposal["provider"] == "claude"
    assert len(secret_calls) == 1
    assert len(calls) == 1
    assert calls[0]["auth_mode"] == "api"
    assert calls[0]["model"] == "sonnet"
    assert calls[0]["api_key"] == "dashboard-anthropic-secret"
    assert "dashboard-anthropic-secret" not in str(calls[0]["prompt"])


def test_hosted_subscription_mode_never_resolves_dashboard_api_key(tmp_path: Path) -> None:
    secret_calls: list[str] = []

    def runner(
        _prompt: str,
        _model: str,
        _auth_mode: str,
        _max_cost_usd: float,
        _max_wall_seconds: int,
        api_key: str | None,
    ) -> str:
        assert api_key is None
        result = "MUNSHI_INTERACTION_RECOVERY=" + json.dumps(
            {"actions": [{"type": "CLICK"}], "reason": "bounded"}
        )
        return json.dumps({"type": "result", "result": result})

    service = InteractionFallbackService(
        tmp_path,
        runner=runner,
        config_resolver=lambda: {
            "enabled": True,
            "authMode": "subscription",
            "model": "sonnet",
            "headless": True,
            "maxTurns": 40,
            "maxCostPerApplicationUsd": 1.0,
            "allowFinalSubmit": False,
            "challengeServiceEnabled": False,
        },
        api_key_resolver=lambda: secret_calls.append("called") or "must-not-be-read",
    )

    service.propose(safe_payload())
    assert secret_calls == []


def test_api_mode_calls_sonnet5_messages_api_without_cli(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            'MUNSHI_INTERACTION_RECOVERY='
                            '{"actions":[{"type":"CLICK"}],"reason":"bounded"}'
                        ),
                    }
                ]
            }

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["json"] = dict(json)
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fallback_module.httpx, "post", fake_post)
    monkeypatch.setattr(
        fallback_module.shutil,
        "which",
        lambda _name: (_ for _ in ()).throw(
            AssertionError("Claude CLI must not be required in API mode")
        ),
    )

    output = fallback_module._default_runner(
        "safe bounded prompt",
        "sonnet",
        "api",
        0.15,
        30,
        "dashboard-anthropic-secret",
    )

    assert "MUNSHI_INTERACTION_RECOVERY=" in output
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "dashboard-anthropic-secret"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["model"] == "claude-sonnet-5"
    assert captured["json"]["max_tokens"] == 768
    assert "dashboard-anthropic-secret" not in str(captured["json"])
