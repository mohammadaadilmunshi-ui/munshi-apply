from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from munshi_apply_native import main
from munshi_apply_native import universal_semantic_interpreter_v1 as semantic_module
from munshi_apply_native.autonomous_apply_credentials import AutonomousApplyConfiguration
from munshi_apply_native.database import Database
from munshi_apply_native.settings import Settings
from munshi_apply_native.universal_semantic_interpreter_v1 import (
    UniversalSemanticInterpretationError,
    UniversalSemanticInterpretationService,
)


def _payload() -> dict[str, object]:
    return {
        "resolver_version": "universal-question-resolver-v1",
        "observation": {
            "raw_question": "Which state are you based out of?",
            "label": "Home base",
            "section_heading": "Contact Information",
            "nearby_text": "City and postal code",
            "placeholder": "Choose one",
            "name": "home_base",
            "id": "field-19",
            "autocomplete": "",
            "input_type": "select",
            "role": "combobox",
            "options": ["New Jersey", "New York", "Pennsylvania"],
            "apply_semantic_type": "UNKNOWN",
            "apply_semantic_confidence": 0.0,
            "control_id": "ctl-19",
            "page_id": "page-1",
            "repeat_group": "",
            "repeat_index": None,
            "previous_labels": ["City"],
            "next_labels": ["ZIP"],
        },
        "ontology_candidates": [
            {
                "concept_id": "contact.region",
                "score": 0.71,
                "sensitivity": "NORMAL",
                "answer_mode": "DIRECT_FACT",
                "category": "CONTACT",
            },
            {
                "concept_id": "contact.city",
                "score": 0.55,
                "sensitivity": "NORMAL",
                "answer_mode": "DIRECT_FACT",
                "category": "CONTACT",
            },
        ],
        "candidate_values": None,
    }


class _Interaction:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def _configuration(self):
        return AutonomousApplyConfiguration(enabled=True, model="sonnet", auth_mode="subscription")

    def _anthropic_api_key(self):  # pragma: no cover - subscription mode must not call
        raise AssertionError("API key must not be requested in subscription mode")

    def runner(self, prompt, model, auth_mode, max_cost_usd, max_wall_seconds, api_key):
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "auth_mode": auth_mode,
                "max_cost_usd": max_cost_usd,
                "max_wall_seconds": max_wall_seconds,
                "api_key": api_key,
            }
        )
        line = "MUNSHI_SEMANTIC_INTERPRETATION=" + json.dumps(self.result)
        return json.dumps({"type": "result", "result": line})


def test_semantic_interpreter_returns_only_candidate_concept_without_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")
    interaction = _Interaction(
        {
            "concept_id": "contact.region",
            "confidence": 0.97,
            "reason_code": "STATE_SELECTION_CONTEXT",
        }
    )
    service = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    )
    result = service.interpret(_payload())
    assert result["concept_id"] == "contact.region"
    assert result["confidence"] == 0.97
    assert result["candidate_values_sent"] is False
    assert result["secret_material_sent"] is False
    assert result["protected_values_sent"] is False
    assert len(interaction.calls) == 1
    prompt = str(interaction.calls[0]["prompt"])
    assert "contact.region" in prompt
    assert "candidate_values" in prompt
    assert '"candidate_values":null' in prompt
    assert "canonical_answer" not in prompt
    assert "execution_value" not in prompt
    assert "password" not in prompt.casefold()
    assert interaction.calls[0]["api_key"] is None


def test_semantic_interpreter_rejects_any_value_bearing_input_before_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")
    interaction = _Interaction({"concept_id": "contact.region", "confidence": 0.97})
    service = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    )
    payload = _payload()
    payload["observation"] = {**dict(payload["observation"]), "value": "New Jersey"}
    with pytest.raises(UniversalSemanticInterpretationError):
        service.interpret(payload)
    assert interaction.calls == []


def test_semantic_interpreter_cannot_select_concept_outside_hunter_candidate_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")
    interaction = _Interaction(
        {"concept_id": "work.authorization.us", "confidence": 0.99, "reason_code": "BAD"}
    )
    service = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    )
    with pytest.raises(UniversalSemanticInterpretationError, match="outside"):
        service.interpret(_payload())


def test_semantic_interpreter_is_default_off_and_does_not_call_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", raising=False)
    interaction = _Interaction({"concept_id": "contact.region", "confidence": 0.99})
    service = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    )
    with pytest.raises(UniversalSemanticInterpretationError, match="disabled"):
        service.interpret(_payload())
    assert interaction.calls == []


def test_semantic_http_endpoint_reuses_owner_auth_and_returns_value_free_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    main.database = Database(tmp_path / "semantic-api.sqlite", migrations)
    main.settings = Settings(
        runtime_root=tmp_path,
        database_path=tmp_path / "semantic-api.sqlite",
        migrations_path=migrations,
        n8n_webhook_url=None,
        n8n_webhook_secret=None,
        outbox_poll_seconds=0.01,
        log_level="INFO",
        command_secret="semantic-command-secret",
    )
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")

    class FakeService:
        def __init__(self, _runtime_root):
            pass

        def interpret(self, payload):
            assert payload["candidate_values"] is None
            return {
                "version": "universal-semantic-interpreter-v1",
                "concept_id": "contact.region",
                "confidence": 0.97,
                "reason_code": "STATE_SELECTION_CONTEXT",
                "provider": "claude",
                "provider_call_made": True,
                "candidate_values_sent": False,
                "secret_material_sent": False,
                "protected_values_sent": False,
            }

    monkeypatch.setattr(main, "UniversalSemanticInterpretationService", FakeService)
    headers = {
        "X-Munshi-Command-Secret": "semantic-command-secret",
        "X-Munshi-Tenant-Id": "tenant-a",
        "X-Munshi-User-Id": "user-a",
    }
    with TestClient(main.app) as client:
        response = client.post(
            "/v1/universal-brain/semantic-interpretation",
            headers=headers,
            json={"payload": _payload()},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["concept_id"] == "contact.region"
    assert body["candidate_values_sent"] is False
    assert "value" not in body


class _DisabledInteraction(_Interaction):
    def _configuration(self):
        return AutonomousApplyConfiguration(
            enabled=False,
            model="sonnet",
            auth_mode="subscription",
        )


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_local_semantic_fallback_is_value_free_and_closed_candidate_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_MODEL", "gemma3:4b")
    interaction = _DisabledInteraction({})
    calls: list[dict[str, object]] = []

    def fake_post(url, *, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeHttpResponse(
            {
                "response": semantic_module.json.dumps(
                    {
                        "concept_id": "contact.region",
                        "confidence": 0.95,
                        "reason_code": "HOME_JURISDICTION_REGION",
                    }
                )
            }
        )

    monkeypatch.setattr(semantic_module.httpx, "post", fake_post)
    service = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    )
    result = service.interpret(_payload())
    assert result["provider"] == "ollama-local"
    assert result["model"] == "gemma3:4b"
    assert result["concept_id"] == "contact.region"
    assert result["confidence"] == 0.95
    assert result["candidate_values_sent"] is False
    assert result["secret_material_sent"] is False
    assert result["protected_values_sent"] is False
    assert len(calls) == 1
    request_body = calls[0]["json"]
    assert isinstance(request_body, dict)
    prompt = str(request_body["prompt"])
    assert '"candidate_values":null' in prompt
    assert '"score":' not in prompt
    assert "Judge confidence independently" in prompt
    assert "canonical_answer" not in prompt
    assert "execution_value" not in prompt
    assert "password" not in prompt.casefold()
    assert calls[0]["url"] == "http://ollama:11434/api/generate"


def test_local_semantic_fallback_rejects_concept_outside_hunter_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_ENABLED", "true")
    interaction = _DisabledInteraction({})

    def fake_post(url, *, json, timeout):
        return _FakeHttpResponse(
            {
                "response": semantic_module.json.dumps(
                    {
                        "concept_id": "work.authorization.us",
                        "confidence": 0.99,
                        "reason_code": "OUTSIDE_SET",
                    }
                )
            }
        )

    monkeypatch.setattr(semantic_module.httpx, "post", fake_post)
    service = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    )
    with pytest.raises(UniversalSemanticInterpretationError, match="outside"):
        service.interpret(_payload())


def test_claude_remains_preferred_when_local_fallback_is_also_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_ENABLED", "true")
    interaction = _Interaction(
        {
            "concept_id": "contact.region",
            "confidence": 0.96,
            "reason_code": "CLAUDE_PRIMARY",
        }
    )

    def unexpected_post(*args, **kwargs):
        raise AssertionError("Local fallback must not run when Claude succeeds")

    monkeypatch.setattr(semantic_module.httpx, "post", unexpected_post)
    service = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    )
    result = service.interpret(_payload())
    assert result["provider"] == "claude"
    assert result["concept_id"] == "contact.region"
    assert len(interaction.calls) == 1


def test_local_semantic_reason_text_is_bounded_observability_not_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_ENABLED", "true")
    interaction = _DisabledInteraction({})

    def fake_post(url, *, json, timeout):
        return _FakeHttpResponse(
            {
                "response": semantic_module.json.dumps(
                    {
                        "concept_id": "contact.region",
                        "confidence": 0.94,
                        "reason_code": "This field is asking for the candidate state or province of residence " * 8,
                    }
                )
            }
        )

    monkeypatch.setattr(semantic_module.httpx, "post", fake_post)
    result = UniversalSemanticInterpretationService(
        tmp_path, interaction_service=interaction  # type: ignore[arg-type]
    ).interpret(_payload())
    assert result["concept_id"] == "contact.region"
    assert result["confidence"] == 0.94
    assert 1 <= len(str(result["reason_code"])) <= 120
    assert " " not in str(result["reason_code"])
    assert result["candidate_values_sent"] is False
