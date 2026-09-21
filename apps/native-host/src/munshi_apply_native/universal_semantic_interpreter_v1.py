"""Bounded value-free semantic interpretation for MUNSHI Universal Brain.

Hunter owns the ontology and all candidate knowledge. Apply/Claude receives only
one browser observation plus a short list of Hunter-proposed ontology concepts.
It may choose a concept identity; it never receives or returns candidate values.
"""
from __future__ import annotations

import json
import os
import re

import httpx
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .interaction_fallback_service import InteractionFallbackError, InteractionFallbackService

SEMANTIC_INTERPRETER_VERSION = "universal-semantic-interpreter-v1"
SEMANTIC_MODEL_ENV = "MUNSHI_UNIVERSAL_MODEL_SEMANTICS_ENABLED"
LOCAL_SEMANTIC_ENV = "MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_ENABLED"
LOCAL_SEMANTIC_MODEL_ENV = "MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_MODEL"
LOCAL_SEMANTIC_TIMEOUT_ENV = "MUNSHI_UNIVERSAL_LOCAL_SEMANTICS_TIMEOUT_SECONDS"
OLLAMA_BASE_URL_ENV = "OLLAMA_BASE_URL"
_DEFAULT_LOCAL_MODEL = "gemma3:4b"
_DEFAULT_OLLAMA_BASE_URL = "http://ollama:11434"
_RESULT_PREFIX = "MUNSHI_SEMANTIC_INTERPRETATION="
_ALLOWED_OBSERVATION_KEYS = frozenset(
    {
        "raw_question", "label", "section_heading", "nearby_text", "placeholder",
        "name", "id", "autocomplete", "input_type", "role", "options",
        "apply_semantic_type", "apply_semantic_confidence", "control_id", "page_id",
        "repeat_group", "repeat_index", "previous_labels", "next_labels",
    }
)
_ALLOWED_CANDIDATE_KEYS = frozenset(
    {"concept_id", "score", "sensitivity", "answer_mode", "category", "description"}
)
_FORBIDDEN_KEY_MARKERS = (
    "answer", "canonical_answer", "execution_value", "display_value", "password",
    "passcode", "otp", "captcha", "secret", "credential", "value_ref", "value",
)


class UniversalSemanticInterpretationError(ValueError):
    pass


def model_semantics_enabled() -> bool:
    return str(os.getenv(SEMANTIC_MODEL_ENV) or "").strip().casefold() in {
        "1", "true", "yes", "on"
    }


def local_semantics_enabled() -> bool:
    return str(os.getenv(LOCAL_SEMANTIC_ENV) or "").strip().casefold() in {
        "1", "true", "yes", "on"
    }


def _safe_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise UniversalSemanticInterpretationError("Semantic interpretation text is too long")
    return text


def _validate_no_forbidden_keys(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().casefold()
            if any(marker == key or key.endswith("_" + marker) for marker in _FORBIDDEN_KEY_MARKERS):
                raise UniversalSemanticInterpretationError(
                    f"Value-bearing or secret field is forbidden in semantic interpretation: {path}.{raw_key}"
                )
            _validate_no_forbidden_keys(child, path=f"{path}.{raw_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_no_forbidden_keys(child, path=f"{path}[{index}]")


def _clean_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if set(payload) - {"resolver_version", "observation", "ontology_candidates", "candidate_values"}:
        raise UniversalSemanticInterpretationError("Unsupported semantic interpretation payload fields")
    if payload.get("candidate_values") is not None:
        raise UniversalSemanticInterpretationError("Candidate values are forbidden in semantic interpretation")
    observation_raw = payload.get("observation")
    candidates_raw = payload.get("ontology_candidates")
    if not isinstance(observation_raw, Mapping):
        raise UniversalSemanticInterpretationError("Semantic interpretation requires an observation")
    if not isinstance(candidates_raw, list) or not 1 <= len(candidates_raw) <= 8:
        raise UniversalSemanticInterpretationError("Semantic interpretation requires one to eight ontology candidates")
    if set(observation_raw) - _ALLOWED_OBSERVATION_KEYS:
        raise UniversalSemanticInterpretationError("Observation contains unsupported fields")

    observation: dict[str, Any] = {}
    for key in _ALLOWED_OBSERVATION_KEYS:
        if key not in observation_raw:
            continue
        value = observation_raw[key]
        if key in {"options", "previous_labels", "next_labels"}:
            if not isinstance(value, list):
                raise UniversalSemanticInterpretationError(f"{key} must be a list")
            maximum = 100 if key == "options" else 20
            observation[key] = [_safe_text(item, limit=300) for item in value[:maximum]]
        elif key == "repeat_index":
            observation[key] = int(value) if value is not None else None
        elif key == "apply_semantic_confidence":
            score = float(value or 0.0)
            observation[key] = max(0.0, min(1.0, score))
        else:
            observation[key] = _safe_text(value, limit=1000)

    candidates: list[dict[str, Any]] = []
    concept_ids: set[str] = set()
    for raw in candidates_raw:
        if not isinstance(raw, Mapping) or set(raw) - _ALLOWED_CANDIDATE_KEYS:
            raise UniversalSemanticInterpretationError("Ontology candidate is invalid")
        concept_id = _safe_text(raw.get("concept_id"), limit=180).casefold()
        if not concept_id or concept_id in concept_ids:
            raise UniversalSemanticInterpretationError("Ontology candidate IDs must be unique")
        concept_ids.add(concept_id)
        candidate = {
            "concept_id": concept_id,
            "score": max(0.0, min(1.0, float(raw.get("score") or 0.0))),
            "sensitivity": _safe_text(raw.get("sensitivity"), limit=40).upper(),
            "answer_mode": _safe_text(raw.get("answer_mode"), limit=80).upper(),
            "category": _safe_text(raw.get("category"), limit=80).upper(),
        }
        if raw.get("description") is not None:
            candidate["description"] = _safe_text(raw.get("description"), limit=500)
        candidates.append(candidate)

    cleaned = {
        "resolver_version": _safe_text(payload.get("resolver_version"), limit=120),
        "observation": observation,
        "ontology_candidates": candidates,
        "candidate_values": None,
    }
    _validate_no_forbidden_keys({"observation": observation, "ontology_candidates": candidates})
    return cleaned


def _parse_model_output(stdout: str) -> dict[str, Any]:
    pieces: list[str] = []
    for raw in str(stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            pieces.append(line)
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "assistant":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        pieces.append(str(block.get("text") or ""))
        elif event.get("type") == "result" and isinstance(event.get("result"), str):
            pieces.append(str(event["result"]))
    joined = "\n".join(pieces)
    matches = re.findall(rf"{re.escape(_RESULT_PREFIX)}\s*(\{{.*\}})", joined)
    if not matches:
        raise UniversalSemanticInterpretationError("Semantic model returned no structured interpretation")
    try:
        result = json.loads(matches[-1])
    except json.JSONDecodeError as error:
        raise UniversalSemanticInterpretationError("Semantic model returned invalid JSON") from error
    if not isinstance(result, dict):
        raise UniversalSemanticInterpretationError("Semantic model result must be an object")
    return result


class UniversalSemanticInterpretationService:
    def __init__(
        self,
        runtime_root: Path,
        *,
        interaction_service: InteractionFallbackService | None = None,
    ) -> None:
        self.interaction = interaction_service or InteractionFallbackService(runtime_root)

    @staticmethod
    def _candidate_ids(cleaned: Mapping[str, Any]) -> list[str]:
        return [
            str(row["concept_id"])
            for row in cleaned["ontology_candidates"]
            if isinstance(row, Mapping)
        ]

    @staticmethod
    def _prompt(cleaned: Mapping[str, Any], candidate_ids: list[str]) -> str:
        return (
            "You are MUNSHI's bounded semantic interpreter. Determine what ONE employer form "
            "control means by choosing only from the supplied canonical ontology candidates. "
            "You receive browser structure and ontology metadata only. Candidate answers, "
            "candidate facts, secrets, protected values and credentials are absent. Never infer "
            "or invent a candidate answer. If none of the candidates is a strong fit, return an "
            "empty concept_id and confidence 0. Use structural context such as section, options, "
            "neighboring labels, input role and repeat group.\nSEMANTIC_INPUT="
            + json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
            + f"\nAllowed concept IDs: {json.dumps(candidate_ids, separators=(',', ':'))}"
        )

    @staticmethod
    def _validate_result(
        result: Mapping[str, Any],
        *,
        candidate_ids: list[str],
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        concept_id = _safe_text(result.get("concept_id"), limit=180).casefold()
        if concept_id and concept_id not in set(candidate_ids):
            raise UniversalSemanticInterpretationError(
                "Semantic model selected a concept outside the candidate set"
            )
        try:
            confidence = float(result.get("confidence") or 0.0)
        except (TypeError, ValueError) as error:
            raise UniversalSemanticInterpretationError(
                "Semantic confidence is invalid"
            ) from error
        if not 0.0 <= confidence <= 1.0:
            raise UniversalSemanticInterpretationError(
                "Semantic confidence is outside 0..1"
            )
        # reason_code is value-free observability metadata, not answer
        # authority. Models sometimes return a short explanation instead of a
        # literal code; normalize it deterministically rather than discarding an
        # otherwise valid closed-set concept decision.
        raw_reason = " ".join(
            str(result.get("reason_code") or "MODEL_SEMANTIC_INTERPRETATION").split()
        )
        reason_code = re.sub(r"[^A-Za-z0-9._:-]+", "_", raw_reason).strip("_")[:120]
        if not reason_code:
            reason_code = "MODEL_SEMANTIC_INTERPRETATION"
        return {
            "version": SEMANTIC_INTERPRETER_VERSION,
            "concept_id": concept_id,
            "confidence": confidence,
            "reason_code": reason_code,
            "provider": provider,
            "model": model,
            "provider_call_made": True,
            "candidate_values_sent": False,
            "secret_material_sent": False,
            "protected_values_sent": False,
        }

    def _interpret_local(
        self,
        cleaned: Mapping[str, Any],
        *,
        candidate_ids: list[str],
    ) -> dict[str, Any]:
        model = str(
            os.getenv(LOCAL_SEMANTIC_MODEL_ENV) or _DEFAULT_LOCAL_MODEL
        ).strip()
        base_url = str(
            os.getenv(OLLAMA_BASE_URL_ENV) or _DEFAULT_OLLAMA_BASE_URL
        ).strip().rstrip("/")
        if not model or not base_url:
            raise UniversalSemanticInterpretationError(
                "Local semantic interpretation provider is not configured"
            )
        try:
            timeout = float(os.getenv(LOCAL_SEMANTIC_TIMEOUT_ENV) or "25")
        except ValueError:
            timeout = 25.0
        # Keep local model confidence independent from deterministic/embedding
        # retrieval scores. The model sees concept identity/meaning but not the
        # numeric score it could simply echo back as its own confidence.
        local_cleaned = dict(cleaned)
        local_cleaned["ontology_candidates"] = [
            {key: value for key, value in dict(row).items() if key != "score"}
            for row in cleaned["ontology_candidates"]
            if isinstance(row, Mapping)
        ]
        prompt = (
            self._prompt(local_cleaned, candidate_ids)
            + "\nJudge confidence independently from retrieval ranking. "
            + "Use confidence >=0.92 only when the field meaning is unambiguous. "
            + '\nReturn JSON only: {"concept_id":"allowed-id-or-empty",'
            '"confidence":0.0,"reason_code":"SHORT_CODE"}'
        )
        try:
            response = httpx.post(
                base_url + "/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
                timeout=max(2.0, min(timeout, 45.0)),
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise UniversalSemanticInterpretationError(
                "Local semantic interpretation failed"
            ) from error
        raw = body.get("response") if isinstance(body, Mapping) else None
        if not isinstance(raw, str) or not raw.strip():
            raise UniversalSemanticInterpretationError(
                "Local semantic model returned no structured interpretation"
            )
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise UniversalSemanticInterpretationError(
                "Local semantic model returned invalid JSON"
            ) from error
        if not isinstance(result, Mapping):
            raise UniversalSemanticInterpretationError(
                "Local semantic model result must be an object"
            )
        return self._validate_result(
            result,
            candidate_ids=candidate_ids,
            provider="ollama-local",
            model=model,
        )

    def interpret(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not model_semantics_enabled():
            raise UniversalSemanticInterpretationError(
                "Universal model semantics are disabled"
            )
        cleaned = _clean_payload(payload)
        candidate_ids = self._candidate_ids(cleaned)
        config = self.interaction._configuration()

        if config.enabled:
            model = config.model.strip()
            if not model:
                raise UniversalSemanticInterpretationError(
                    "Semantic interpretation model is not configured"
                )
            api_key = (
                self.interaction._anthropic_api_key()
                if config.auth_mode == "api"
                else None
            )
            prompt = (
                self._prompt(cleaned, candidate_ids)
                + f"\nOutput exactly one line: {_RESULT_PREFIX}"
                + '{"concept_id":"allowed-id-or-empty","confidence":0.0,'
                '"reason_code":"SHORT_CODE"}'
            )
            try:
                stdout = self.interaction.runner(
                    prompt,
                    model,
                    config.auth_mode,
                    min(max(config.max_cost_per_application_usd, 0.01), 0.05),
                    20,
                    api_key,
                )
                result = _parse_model_output(stdout)
                return self._validate_result(
                    result,
                    candidate_ids=candidate_ids,
                    provider="claude",
                    model=model,
                )
            except (InteractionFallbackError, UniversalSemanticInterpretationError):
                if not local_semantics_enabled():
                    raise

        if local_semantics_enabled():
            return self._interpret_local(cleaned, candidate_ids=candidate_ids)

        raise UniversalSemanticInterpretationError(
            "Autonomous Apply model fallback is disabled"
        )
