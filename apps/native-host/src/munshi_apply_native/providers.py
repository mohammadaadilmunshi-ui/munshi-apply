from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


@dataclass(frozen=True)
class ProviderContextItem:
    evidence_id: str
    source: str
    text: str
    trust_level: str


@dataclass(frozen=True)
class ProviderGenerationRequest:
    model: str
    question: str
    semantic_type: str
    context: tuple[ProviderContextItem, ...]
    max_words: int | None = None
    max_output_tokens: int = 512


@dataclass(frozen=True)
class ProviderClaim:
    claim_id: str
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ProviderGenerationResult:
    response_id: str
    model: str
    text: str
    claims: tuple[ProviderClaim, ...]
    usage: ProviderUsage


class AIProvider(Protocol):
    def generate_structured(
        self, request: ProviderGenerationRequest
    ) -> ProviderGenerationResult: ...


Transport = Callable[[urllib_request.Request, float], dict[str, object]]


def _default_transport(request: urllib_request.Request, timeout: float) -> dict[str, object]:
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as error:
        raise ValueError(f"OpenAI generation failed (HTTP {error.code})") from error
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError("OpenAI generation failed") from error
    if not isinstance(payload, dict):
        raise ValueError("OpenAI returned an invalid response")
    return payload


def _structured_output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "text": {"type": "string"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "claimId": {"type": "string"},
                        "text": {"type": "string"},
                        "evidenceIds": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["claimId", "text", "evidenceIds"],
                },
            },
        },
        "required": ["text", "claims"],
    }


def _input_text(request: ProviderGenerationRequest) -> str:
    evidence = [
        {
            "evidenceId": item.evidence_id,
            "source": item.source,
            "trustLevel": item.trust_level,
            "text": item.text,
        }
        for item in request.context
    ]
    payload: dict[str, object] = {
        "question": request.question,
        "semanticType": request.semantic_type,
        "evidence": evidence,
    }
    if request.max_words is not None:
        payload["maxWords"] = request.max_words
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _validate_response_status(payload: dict[str, object]) -> None:
    status = payload.get("status")
    if status == "completed":
        return
    if status == "failed":
        raise ValueError("OpenAI generation failed: response status is failed")
    if status == "incomplete":
        details = payload.get("incomplete_details")
        if isinstance(details, dict) and isinstance(details.get("reason"), str):
            raise ValueError(f"OpenAI generation is incomplete ({details['reason']})")
        raise ValueError("OpenAI generation is incomplete")
    raise ValueError("OpenAI response is not completed")


def _extract_output_text(payload: dict[str, object]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        raise ValueError("OpenAI response does not contain output items")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise ValueError("OpenAI refused the generation request")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    if not texts:
        raise ValueError("OpenAI response does not contain structured output text")
    return "".join(texts)


def _parse_usage(payload: dict[str, object]) -> ProviderUsage:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("OpenAI response does not include token usage")
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    token_values = (input_tokens, output_tokens, total_tokens)
    if not all(isinstance(value, int) and value >= 0 for value in token_values):
        raise ValueError("OpenAI response includes invalid token usage")
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _parse_structured_draft(value: str) -> tuple[str, tuple[ProviderClaim, ...]]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("OpenAI structured output is not valid JSON") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError("OpenAI structured output is incomplete")
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list):
        raise ValueError("OpenAI structured output does not include claims")
    claims: list[ProviderClaim] = []
    for item in raw_claims:
        if not isinstance(item, dict):
            raise ValueError("OpenAI claim is invalid")
        claim_id = item.get("claimId")
        text = item.get("text")
        evidence_ids = item.get("evidenceIds")
        if (
            not isinstance(claim_id, str)
            or not claim_id.strip()
            or not isinstance(text, str)
            or not text.strip()
            or not isinstance(evidence_ids, list)
            or not all(isinstance(evidence_id, str) and evidence_id for evidence_id in evidence_ids)
        ):
            raise ValueError("OpenAI claim is incomplete")
        claims.append(
            ProviderClaim(
                claim_id=claim_id,
                text=text,
                evidence_ids=tuple(evidence_ids),
            )
        )
    return payload["text"], tuple(claims)


class OpenAIResponsesProvider:
    def __init__(
        self,
        api_key: str,
        *,
        transport: Transport = _default_transport,
        timeout_seconds: float = 30.0,
    ) -> None:
        if len(api_key.strip()) < 20:
            raise ValueError("OpenAI API key is incomplete")
        if timeout_seconds <= 0:
            raise ValueError("Provider timeout must be positive")
        self._api_key = api_key.strip()
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    def generate_structured(
        self, request: ProviderGenerationRequest
    ) -> ProviderGenerationResult:
        if not request.model.strip():
            raise ValueError("OpenAI model is required")
        if not request.question.strip():
            raise ValueError("Application question is required")
        if not request.context:
            raise ValueError("Verified evidence context is required")
        if request.max_words is not None and request.max_words < 1:
            raise ValueError("max_words must be positive")
        if not 1 <= request.max_output_tokens <= 4096:
            raise ValueError("max_output_tokens must be between 1 and 4096")

        body = {
            "model": request.model,
            "store": False,
            "max_output_tokens": request.max_output_tokens,
            "instructions": (
                "You draft one job-application answer using only the supplied evidence. "
                "Do not add facts, metrics, employers, dates, credentials, immigration facts, "
                "or claims that are not supported by the supplied evidence. Every factual claim "
                "must cite one or more supplied evidenceId values in the structured claims array."
            ),
            "input": _input_text(request),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "munshi_application_draft",
                    "strict": True,
                    "schema": _structured_output_schema(),
                }
            },
        }
        http_request = urllib_request.Request(  # noqa: S310
            _OPENAI_RESPONSES_URL,
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "MUNSHI-Apply/0.2",
            },
        )
        payload = self._transport(http_request, self._timeout_seconds)
        _validate_response_status(payload)
        response_id = payload.get("id")
        response_model = payload.get("model")
        if not isinstance(response_id, str) or not response_id:
            raise ValueError("OpenAI response is missing an id")
        if not isinstance(response_model, str) or not response_model:
            raise ValueError("OpenAI response is missing a model")
        draft_text, claims = _parse_structured_draft(_extract_output_text(payload))
        return ProviderGenerationResult(
            response_id=response_id,
            model=response_model,
            text=draft_text,
            claims=claims,
            usage=_parse_usage(payload),
        )
