from __future__ import annotations

import json
from urllib import request as urllib_request

import pytest

from munshi_apply_native.providers import (
    OpenAIResponsesProvider,
    ProviderContextItem,
    ProviderGenerationRequest,
)


def generation_request() -> ProviderGenerationRequest:
    return ProviderGenerationRequest(
        model="gpt-test",
        question="Describe your recruiting experience.",
        semantic_type="RELEVANT_EXPERIENCE",
        context=(
            ProviderContextItem(
                evidence_id="e-1",
                source="verified-employment",
                text="Verified recruiting and onboarding experience",
                trust_level="VERIFIED",
            ),
        ),
        max_words=80,
        max_output_tokens=256,
    )


def successful_payload() -> dict[str, object]:
    return {
        "id": "resp-1",
        "model": "gpt-test-2026-08-01",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "text": "I have verified recruiting and onboarding experience.",
                                "claims": [
                                    {
                                        "claimId": "claim-1",
                                        "text": "I have recruiting and onboarding experience.",
                                        "evidenceIds": ["e-1"],
                                    }
                                ],
                            }
                        ),
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
        },
    }


def test_openai_provider_uses_private_structured_responses_request() -> None:
    captured: dict[str, object] = {}

    def transport(request: urllib_request.Request, timeout: float) -> dict[str, object]:
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads((request.data or b"").decode("utf-8"))
        captured["timeout"] = timeout
        return successful_payload()

    provider = OpenAIResponsesProvider(
        "sk-proj-test_" + ("x" * 40), transport=transport, timeout_seconds=12
    )
    result = provider.generate_structured(generation_request())

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 12
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["store"] is False
    assert body["max_output_tokens"] == 256
    assert "tools" not in body
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert result.response_id == "resp-1"
    assert result.text.startswith("I have verified")
    assert result.claims[0].evidence_ids == ("e-1",)
    assert result.usage.total_tokens == 150


def test_provider_input_contains_only_bounded_context_supplied_by_caller() -> None:
    captured: dict[str, object] = {}

    def transport(request: urllib_request.Request, timeout: float) -> dict[str, object]:
        del timeout
        captured["body"] = json.loads((request.data or b"").decode("utf-8"))
        return successful_payload()

    provider = OpenAIResponsesProvider("sk-proj-test_" + ("x" * 40), transport=transport)
    provider.generate_structured(generation_request())

    body = captured["body"]
    assert isinstance(body, dict)
    application_input = json.loads(body["input"])
    assert application_input["evidence"] == [
        {
            "evidenceId": "e-1",
            "source": "verified-employment",
            "trustLevel": "VERIFIED",
            "text": "Verified recruiting and onboarding experience",
        }
    ]
    assert application_input["maxWords"] == 80


def test_provider_rejects_missing_verified_context_before_network() -> None:
    called = False

    def transport(request: urllib_request.Request, timeout: float) -> dict[str, object]:
        nonlocal called
        del request, timeout
        called = True
        return successful_payload()

    provider = OpenAIResponsesProvider("sk-proj-test_" + ("x" * 40), transport=transport)
    request = generation_request()
    empty = ProviderGenerationRequest(
        model=request.model,
        question=request.question,
        semantic_type=request.semantic_type,
        context=(),
        max_words=request.max_words,
        max_output_tokens=request.max_output_tokens,
    )

    with pytest.raises(ValueError, match="Verified evidence context is required"):
        provider.generate_structured(empty)
    assert called is False


def test_provider_rejects_unstructured_or_unsupported_output() -> None:
    def no_claim_transport(
        request: urllib_request.Request, timeout: float
    ) -> dict[str, object]:
        del request, timeout
        payload = successful_payload()
        payload["output"] = [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": '{"text":"draft"}'}],
            }
        ]
        return payload

    provider = OpenAIResponsesProvider(
        "sk-proj-test_" + ("x" * 40), transport=no_claim_transport
    )
    with pytest.raises(ValueError, match="does not include claims"):
        provider.generate_structured(generation_request())


def test_provider_requires_usage_for_budget_accounting() -> None:
    def missing_usage(
        request: urllib_request.Request, timeout: float
    ) -> dict[str, object]:
        del request, timeout
        payload = successful_payload()
        payload.pop("usage")
        return payload

    provider = OpenAIResponsesProvider("sk-proj-test_" + ("x" * 40), transport=missing_usage)
    with pytest.raises(ValueError, match="does not include token usage"):
        provider.generate_structured(generation_request())


def test_provider_rejects_incomplete_response_before_parsing_draft() -> None:
    def incomplete(
        request: urllib_request.Request, timeout: float
    ) -> dict[str, object]:
        del request, timeout
        payload = successful_payload()
        payload["status"] = "incomplete"
        payload["incomplete_details"] = {"reason": "max_output_tokens"}
        return payload

    provider = OpenAIResponsesProvider("sk-proj-test_" + ("x" * 40), transport=incomplete)
    with pytest.raises(ValueError, match="incomplete .*max_output_tokens"):
        provider.generate_structured(generation_request())


def test_provider_rejects_refusal_content() -> None:
    def refusal(request: urllib_request.Request, timeout: float) -> dict[str, object]:
        del request, timeout
        payload = successful_payload()
        payload["output"] = [
            {
                "type": "message",
                "content": [{"type": "refusal", "refusal": "cannot comply"}],
            }
        ]
        return payload

    provider = OpenAIResponsesProvider("sk-proj-test_" + ("x" * 40), transport=refusal)
    with pytest.raises(ValueError, match="refused"):
        provider.generate_structured(generation_request())


def test_provider_rejects_unbounded_output_token_request_before_network() -> None:
    called = False

    def transport(request: urllib_request.Request, timeout: float) -> dict[str, object]:
        nonlocal called
        del request, timeout
        called = True
        return successful_payload()

    provider = OpenAIResponsesProvider("sk-proj-test_" + ("x" * 40), transport=transport)
    request = generation_request()
    invalid = ProviderGenerationRequest(
        model=request.model,
        question=request.question,
        semantic_type=request.semantic_type,
        context=request.context,
        max_words=request.max_words,
        max_output_tokens=5000,
    )
    with pytest.raises(ValueError, match="max_output_tokens"):
        provider.generate_structured(invalid)
    assert called is False
