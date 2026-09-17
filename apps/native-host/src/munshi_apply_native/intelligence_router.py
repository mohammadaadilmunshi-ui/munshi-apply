from __future__ import annotations

from dataclasses import dataclass

from .ai_settings import AIConfiguration, AISettingsStore
from .response_planner import JobResponsePlan


@dataclass(frozen=True)
class IntelligenceRoute:
    provider: str
    model: str
    lane: str
    local: bool
    fallback_provider: str | None
    fallback_model: str | None
    reason: str


def choose_intelligence_route(
    config: AIConfiguration,
    store: AISettingsStore,
    plan: JobResponsePlan,
) -> IntelligenceRoute:
    openai_model = config.openai_model_for_lane(plan.model_lane)
    ollama_model = config.ollama_model.strip()
    has_openai = store.key_source() != "none" and bool(openai_model)
    has_ollama = bool(ollama_model)

    if config.provider == "openai":
        if not has_openai:
            raise ValueError("OpenAI is selected but its credential/model is not configured")
        return IntelligenceRoute(
            provider="openai",
            model=openai_model,
            lane=plan.model_lane,
            local=False,
            fallback_provider="ollama" if config.prefer_local_fallback and has_ollama else None,
            fallback_model=ollama_model if config.prefer_local_fallback and has_ollama else None,
            reason=f"{plan.model_lane.lower()} model lane selected for {plan.intent}",
        )

    if config.provider == "ollama":
        if not has_ollama:
            raise ValueError("Ollama is selected but no local model is configured")
        return IntelligenceRoute(
            provider="ollama",
            model=ollama_model,
            lane=plan.model_lane,
            local=True,
            fallback_provider=None,
            fallback_model=None,
            reason=f"owner selected local Ollama for {plan.intent}",
        )

    if config.prefer_local_fallback and has_ollama:
        return IntelligenceRoute(
            provider="ollama",
            model=ollama_model,
            lane=plan.model_lane,
            local=True,
            fallback_provider="openai" if has_openai else None,
            fallback_model=openai_model if has_openai else None,
            reason="auto routing prefers configured local inference",
        )
    if has_openai:
        return IntelligenceRoute(
            provider="openai",
            model=openai_model,
            lane=plan.model_lane,
            local=False,
            fallback_provider="ollama" if has_ollama else None,
            fallback_model=ollama_model if has_ollama else None,
            reason=f"auto routing selected OpenAI {plan.model_lane.lower()} lane",
        )
    if has_ollama:
        return IntelligenceRoute(
            provider="ollama",
            model=ollama_model,
            lane=plan.model_lane,
            local=True,
            fallback_provider=None,
            fallback_model=None,
            reason="auto routing used the only configured provider",
        )
    raise ValueError("No configured AI provider is available")
