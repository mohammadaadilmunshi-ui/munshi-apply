from __future__ import annotations

from munshi_apply_native.ai_settings import AIConfiguration
from munshi_apply_native.intelligence_router import choose_intelligence_route
from munshi_apply_native.response_planner import plan_job_response


class FakeStore:
    def __init__(self, source: str) -> None:
        self.source = source

    def key_source(self) -> str:
        return self.source


def test_auto_route_can_prefer_local_and_retain_openai_fallback() -> None:
    config = AIConfiguration(
        provider="auto",
        enabled=True,
        model="cheap",
        cheap_model="cheap",
        strong_model="strong",
        ollama_model="qwen-local",
        prefer_local_fallback=True,
    )
    route = choose_intelligence_route(
        config,
        FakeStore("keychain"),  # type: ignore[arg-type]
        plan_job_response("Why this role?", "WHY_ROLE"),
    )
    assert route.provider == "ollama"
    assert route.fallback_provider == "openai"


def test_strong_lane_selects_strong_openai_model() -> None:
    config = AIConfiguration(
        provider="openai",
        enabled=True,
        model="cheap",
        cheap_model="cheap",
        strong_model="strong",
        prefer_local_fallback=False,
    )
    route = choose_intelligence_route(
        config,
        FakeStore("keychain"),  # type: ignore[arg-type]
        plan_job_response("Tell us about a time you solved a conflict", "BEHAVIORAL_EXAMPLE"),
    )
    assert route.provider == "openai"
    assert route.model == "strong"
    assert route.lane == "STRONG"
