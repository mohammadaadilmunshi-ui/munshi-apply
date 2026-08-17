from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from .ai_budget_store import AIBudgetStore
from .ai_draft_store import AIDraftStore
from .ai_settings import AIConfiguration, AISettingsStore
from .application_store import ApplicationStore
from .architecture_store import ArchitectureStore
from .database import Database
from .intelligence_router import IntelligenceRoute, choose_intelligence_route
from .profile_store import ProfileStore
from .providers import (
    OllamaChatProvider,
    OpenAIResponsesProvider,
    ProviderContextItem,
    ProviderGenerationRequest,
    ProviderGenerationResult,
)
from .response_planner import JobResponsePlan, plan_job_response
from .writing_style import WritingStyleStore

_SAFE_DRAFT_SEMANTIC_TYPES = frozenset(
    {
        "WHY_COMPANY",
        "WHY_ROLE",
        "RELEVANT_EXPERIENCE",
        "CAREER_GOALS",
        "BEHAVIORAL_EXAMPLE",
        "ROLE_RESPONSIBILITIES",
        "ROLE_UNDERSTANDING",
        "MOTIVATION",
        "RECRUITMENT_MOTIVATION",
    }
)
_AUTHORITATIVE_TRUST = frozenset({"VERIFIED", "USER_CONFIRMED", "DOCUMENT_CONFIRMED"})
_PROFILE_EVIDENCE_KINDS = frozenset(
    {
        "PROFILE_FACT",
        "EMPLOYMENT",
        "EDUCATION",
        "PROJECT",
        "CERTIFICATION",
        "USER_CONFIRMED_ANSWER",
    }
)
_ALWAYS_ALLOWED_EVIDENCE_KINDS = frozenset({"JOB_REQUIREMENT", "COMPANY_CONTEXT"})
_MAX_CONTEXT_ITEMS = 7
_MAX_CONTEXT_CHARACTERS = 8_000
_MAX_OUTPUT_TOKENS = 1_024
_PRICING_MAX_AGE_DAYS = 30
_PRICING_VERIFIED_AT = datetime(2026, 8, 14, tzinfo=UTC)
_PRICING_SOURCE = "OpenAI API pricing and model pages, verified 2026-08-14"


@dataclass(frozen=True)
class PricingSnapshot:
    provider: str
    model: str
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float


_PRICING = {
    "gpt-5.6": PricingSnapshot("openai", "gpt-5.6", 5.0, 30.0),
    "gpt-5.6-sol": PricingSnapshot("openai", "gpt-5.6-sol", 5.0, 30.0),
    "gpt-5.6-terra": PricingSnapshot("openai", "gpt-5.6-terra", 2.5, 15.0),
    "gpt-5.6-luna": PricingSnapshot("openai", "gpt-5.6-luna", 1.0, 6.0),
}

ProviderFactory = Callable[[str], OpenAIResponsesProvider]
OllamaProviderFactory = Callable[[], OllamaChatProvider]
Clock = Callable[[], datetime]


def _default_provider_factory(api_key: str) -> OpenAIResponsesProvider:
    return OpenAIResponsesProvider(api_key)


def _default_ollama_provider_factory() -> OllamaChatProvider:
    return OllamaChatProvider()


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _words(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 2}


def _cost(pricing: PricingSnapshot, input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * pricing.input_usd_per_million_tokens
        + (output_tokens / 1_000_000) * pricing.output_usd_per_million_tokens,
        8,
    )


class AIGovernanceService:
    """Native truth, evidence, pricing, and budget boundary for paid AI generation."""

    def __init__(
        self,
        database: Database,
        ai_store: AISettingsStore,
        *,
        provider_factory: ProviderFactory = _default_provider_factory,
        ollama_provider_factory: OllamaProviderFactory = _default_ollama_provider_factory,
        clock: Clock = _default_clock,
    ) -> None:
        self.database = database
        self.ai_store = ai_store
        self.provider_factory = provider_factory
        self.ollama_provider_factory = ollama_provider_factory
        self.clock = clock
        self.architecture = ArchitectureStore(database)
        self.applications = ApplicationStore(database)
        self.budget = AIBudgetStore(database)
        self.drafts = AIDraftStore(database)

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("AI governance clock must be timezone-aware")
        return now.astimezone(UTC)

    def _pricing(self, model: str, *, now: datetime) -> PricingSnapshot:
        pricing = _PRICING.get(model)
        if pricing is None:
            raise ValueError("Selected model has no verified MUNSHI pricing snapshot")
        age_days = (now - _PRICING_VERIFIED_AT).total_seconds() / 86_400
        if age_days < 0 or age_days > _PRICING_MAX_AGE_DAYS:
            raise ValueError(
                "OpenAI pricing snapshot is stale and must be re-verified before paid usage"
            )
        return pricing

    def _pricing_status(self, model: str, *, now: datetime) -> dict[str, object] | None:
        pricing = _PRICING.get(model)
        if pricing is None:
            return None
        age_days = max(0, int((now - _PRICING_VERIFIED_AT).total_seconds() // 86_400))
        return {
            "provider": pricing.provider,
            "model": pricing.model,
            "inputUsdPerMillionTokens": pricing.input_usd_per_million_tokens,
            "outputUsdPerMillionTokens": pricing.output_usd_per_million_tokens,
            "verifiedAt": _PRICING_VERIFIED_AT.isoformat(),
            "source": _PRICING_SOURCE,
            "ageDays": age_days,
            "stale": age_days > _PRICING_MAX_AGE_DAYS,
        }

    def control_status(self) -> dict[str, object]:
        now = self._now()
        config = self.ai_store.load()
        settings = self.ai_store.status()
        usage = self.budget.usage_summary(
            at=now.isoformat(), monthly_budget_usd=config.monthly_budget_usd
        )
        return {
            "settings": settings,
            "usage": usage,
            "pricing": (
                self._pricing_status(config.openai_model_for_lane("CHEAP"), now=now)
                if config.provider != "ollama"
                else None
            ),
            "guardrails": {
                "safeDraftSemanticTypes": sorted(_SAFE_DRAFT_SEMANTIC_TYPES),
                "consequentialQuestionsManual": True,
                "protectedEvidenceExcluded": True,
                "ownerReviewRequired": True,
                "finalSubmissionManual": True,
            },
        }

    @staticmethod
    def _validate_request(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("AI draft request must be an object")
        application_id = payload.get("applicationId")
        page_id = payload.get("pageId")
        question_id = payload.get("questionId")
        control_id = payload.get("controlId")
        question = payload.get("question")
        semantic_type = payload.get("semanticType")
        correlation_id = payload.get("correlationId")
        if not isinstance(application_id, str) or not application_id.strip():
            raise ValueError("AI draft request requires applicationId")
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError("AI draft request requires pageId")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("AI draft request requires questionId")
        if not isinstance(control_id, str) or not control_id.strip():
            raise ValueError("AI draft request requires controlId")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("AI draft request requires question")
        if not isinstance(semantic_type, str) or not semantic_type.strip():
            raise ValueError("AI draft request requires semanticType")
        if not isinstance(correlation_id, str) or not correlation_id.strip():
            raise ValueError("AI draft request requires correlationId")
        max_words = payload.get("maxWords")
        if max_words is not None and (
            not isinstance(max_words, int)
            or isinstance(max_words, bool)
            or not 1 <= max_words <= 500
        ):
            raise ValueError("AI draft maxWords must be an integer between 1 and 500")
        page_context = payload.get("pageContext", "")
        if page_context is not None and not isinstance(page_context, str):
            raise ValueError("AI draft pageContext must be a string")
        page_context = (page_context or "").strip()
        if len(page_context) > 20_000:
            raise ValueError("AI draft pageContext exceeds 20,000 characters")
        max_output_tokens = payload.get("maxOutputTokens", 512)
        if (
            not isinstance(max_output_tokens, int)
            or isinstance(max_output_tokens, bool)
            or not 1 <= max_output_tokens <= _MAX_OUTPUT_TOKENS
        ):
            raise ValueError(f"AI draft maxOutputTokens must be between 1 and {_MAX_OUTPUT_TOKENS}")
        return {
            "applicationId": application_id.strip(),
            "pageId": page_id.strip(),
            "questionId": question_id.strip(),
            "controlId": control_id.strip(),
            "question": question.strip(),
            "semanticType": semantic_type.strip(),
            "pageContext": page_context,
            "correlationId": correlation_id.strip(),
            "maxWords": max_words,
            "maxOutputTokens": max_output_tokens,
        }

    @staticmethod
    def _allowed_kinds(config: AIConfiguration) -> set[str]:
        kinds = set(_ALWAYS_ALLOWED_EVIDENCE_KINDS)
        if config.allow_profile_evidence:
            kinds.update(_PROFILE_EVIDENCE_KINDS)
        if config.allow_resume_evidence:
            kinds.add("RESUME_BULLET")
        return kinds

    def _context(
        self,
        *,
        application_id: str,
        question: str,
        semantic_type: str,
        page_context: str,
        config: AIConfiguration,
    ) -> tuple[tuple[ProviderContextItem, ...], set[str], dict[str, object]]:
        graph = self.architecture.evidence_graph(application_id)
        retrieval_terms = getattr(self, "_active_retrieval_terms", ())
        query_tokens = _words(question + " " + " ".join(retrieval_terms))
        allowed_kinds = self._allowed_kinds(config)
        candidates: list[tuple[float, dict[str, object]]] = []
        if page_context:
            page_evidence_id = (
                "job-context-" + hashlib.sha256(page_context.encode("utf-8")).hexdigest()[:20]
            )
            candidates.append(
                (
                    1.0,
                    {
                        "evidence_id": page_evidence_id,
                        "kind": "JOB_REQUIREMENT",
                        "text": page_context,
                        "semantic_types": [semantic_type],
                        "trust_level": "DOCUMENT_CONFIRMED",
                        "protected": False,
                        "source": "current-employer-page",
                        "updated_at": self._now().isoformat(),
                    },
                )
            )

        profile = ProfileStore(self.database).latest()
        if profile:
            if config.allow_profile_evidence:
                for fact in profile.get("facts", []):
                    if fact.get("protected") or fact.get("trustLevel") not in _AUTHORITATIVE_TRUST:
                        continue
                    value = str(fact.get("value", "")).strip()
                    if not value:
                        continue
                    candidates.append(
                        (
                            0.58,
                            {
                                "evidence_id": "profile-" + str(fact.get("factId", "unknown")),
                                "kind": "PROFILE_FACT",
                                "text": f"{fact.get('key', 'profile fact')}: {value}",
                                "semantic_types": [],
                                "trust_level": fact.get("trustLevel"),
                                "protected": False,
                                "source": "confirmed-profile",
                                "updated_at": fact.get("updatedAt", self._now().isoformat()),
                            },
                        )
                    )
            for record in profile.get("records", []):
                if record.get("kind") not in {
                    "EMPLOYMENT",
                    "PROJECT",
                    "EDUCATION",
                    "CERTIFICATION",
                }:
                    continue
                for fact in record.get("facts", []):
                    if fact.get("protected") or fact.get("trustLevel") not in _AUTHORITATIVE_TRUST:
                        continue
                    key = str(fact.get("key", ""))
                    if not config.allow_profile_evidence and not (
                        config.allow_resume_evidence
                        and key
                        in {
                            "responsibilities",
                            "achievements",
                            "project_summary",
                            "project_technologies",
                            "gpa",
                        }
                    ):
                        continue
                    value = str(fact.get("value", "")).strip()
                    if not value:
                        continue
                    kind = (
                        "RESUME_BULLET"
                        if key
                        in {
                            "responsibilities",
                            "achievements",
                            "project_summary",
                            "project_technologies",
                        }
                        else str(record.get("kind"))
                    )
                    candidates.append(
                        (
                            0.72 if kind == "RESUME_BULLET" else 0.62,
                            {
                                "evidence_id": "record-" + str(fact.get("factId", "unknown")),
                                "kind": kind,
                                "text": (
                                    f"{record.get('label', record.get('kind', 'record'))}: {value}"
                                ),
                                "semantic_types": [],
                                "trust_level": fact.get("trustLevel"),
                                "protected": False,
                                "source": "confirmed-profile-record",
                                "updated_at": fact.get("updatedAt", self._now().isoformat()),
                            },
                        )
                    )

        blocked_protected = 0
        blocked_trust = 0
        blocked_kind = 0
        for raw_node in graph["nodes"]:
            node = dict(raw_node)
            if bool(node.get("protected")):
                blocked_protected += 1
                continue
            if node.get("trust_level") not in _AUTHORITATIVE_TRUST:
                blocked_trust += 1
                continue
            if node.get("kind") not in allowed_kinds:
                blocked_kind += 1
                continue
            semantic_types = node.get("semantic_types")
            semantic_match = isinstance(semantic_types, list) and semantic_type in semantic_types
            text = str(node.get("text", ""))
            evidence_tokens = _words(text)
            overlap = (
                len(query_tokens & evidence_tokens) / len(query_tokens)
                if query_tokens and evidence_tokens
                else 0.0
            )
            if not semantic_match and overlap == 0:
                continue
            score = (0.8 if semantic_match else 0.15 * overlap) + (
                0.2 * overlap if semantic_match else 0
            )
            candidates.append((score, node))
        candidates.sort(
            key=lambda item: (
                -item[0],
                -len(str(item[1].get("updated_at", ""))),
                str(item[1].get("evidence_id", "")),
            )
        )
        selected: list[ProviderContextItem] = []
        selected_ids: set[str] = set()
        selected_texts: set[str] = set()
        source_counts: dict[str, int] = {}
        characters = 0
        for _, node in candidates:
            if len(selected) >= _MAX_CONTEXT_ITEMS:
                break
            text = str(node.get("text", "")).strip()
            if not text or characters + len(text) > _MAX_CONTEXT_CHARACTERS:
                continue
            evidence_id = str(node.get("evidence_id", "")).strip()
            source = str(node.get("source", "")).strip()
            trust = str(node.get("trust_level", "")).strip()
            normalized_text = " ".join(text.lower().split())
            if not evidence_id or not source or not trust or normalized_text in selected_texts:
                continue
            if source_counts.get(source, 0) >= 3:
                continue
            selected.append(ProviderContextItem(evidence_id, source, text, trust))
            selected_texts.add(normalized_text)
            source_counts[source] = source_counts.get(source, 0) + 1
            selected_ids.add(evidence_id)
            characters += len(text)
        if not selected:
            raise ValueError(
                "No authoritative non-protected evidence is available for this AI draft"
            )
        contradiction = any(
            edge.get("relation") == "CONTRADICTS"
            and edge.get("from_evidence_id") in selected_ids
            and edge.get("to_evidence_id") in selected_ids
            for edge in graph["edges"]
        )
        if contradiction:
            raise ValueError("Selected authoritative evidence contains an unresolved contradiction")
        return (
            tuple(selected),
            selected_ids,
            {
                "blockedProtectedCount": blocked_protected,
                "blockedTrustCount": blocked_trust,
                "blockedKindCount": blocked_kind,
                "characterCount": characters,
            },
        )

    def _prepare(self, payload: object, *, reserve: bool) -> dict[str, object]:
        request = self._validate_request(payload)
        now = self._now()
        config = self.ai_store.load()
        if not config.enabled:
            raise ValueError("AI features are disabled by the owner")
        if not config.allow_application_drafts:
            raise ValueError("AI application drafting is disabled by the owner")
        semantic_type = str(request["semanticType"])
        plan = plan_job_response(
            str(request["question"]),
            semantic_type,
            request["maxWords"] if isinstance(request["maxWords"], int) else None,
        )
        if semantic_type not in _SAFE_DRAFT_SEMANTIC_TYPES:
            raise ValueError("This application question type is not eligible for AI generation")
        route = choose_intelligence_route(config, self.ai_store, plan)
        self._active_retrieval_terms = plan.retrieval_terms
        try:
            context, evidence_ids, evidence_stats = self._context(
                application_id=str(request["applicationId"]),
                question=str(request["question"]),
                semantic_type=semantic_type,
                page_context=str(request.get("pageContext", "")),
                config=config,
            )
        finally:
            self._active_retrieval_terms = ()
        if plan.requires_job_context and not any(
            item.source == "current-employer-page" or "job" in item.source.lower()
            for item in context
        ):
            raise ValueError(
                "This response needs job/company context; open the job listing in this tab first"
            )
        style = WritingStyleStore(self.ai_store.runtime_root).load()
        estimated_input_tokens = 2_048 + len(str(request["question"]).encode("utf-8"))
        estimated_input_tokens += sum(len(item.text.encode("utf-8")) for item in context)
        max_output_tokens = int(request["maxOutputTokens"])
        pricing: PricingSnapshot | None = None
        reservation_id: str | None = None
        if route.provider == "openai":
            pricing = self._pricing(route.model, now=now)
            planned_cost = _cost(pricing, estimated_input_tokens, max_output_tokens)
            budget_args = {
                "planned_cost_usd": planned_cost,
                "monthly_budget_usd": config.monthly_budget_usd,
                "warning_budget_usd": config.warning_budget_usd,
                "hard_stop": config.hard_stop,
                "at": now.isoformat(),
            }
            if reserve:
                reservation_id = f"ai-res-{uuid.uuid4()}"
                decision = self.budget.reserve(
                    reservation_id=reservation_id,
                    provider="openai",
                    model=route.model,
                    correlation_id=str(request["correlationId"]),
                    **budget_args,
                )
            else:
                decision = self.budget.evaluate(**budget_args)
            if decision["state"] == "BLOCK":
                if route.fallback_provider == "ollama" and route.fallback_model:
                    route = IntelligenceRoute(
                        provider="ollama",
                        model=route.fallback_model,
                        lane=route.lane,
                        local=True,
                        fallback_provider=None,
                        fallback_model=None,
                        reason="paid route blocked by budget; local Ollama fallback selected",
                    )
                    pricing = None
                    reservation_id = None
                    planned_cost = 0.0
                    decision = {
                        "state": "ALLOW",
                        "month": now.strftime("%Y-%m"),
                        "spentUsd": self.budget.usage_summary(
                            at=now.isoformat(), monthly_budget_usd=config.monthly_budget_usd
                        )["spentUsd"],
                        "reservedUsd": 0.0,
                        "plannedCostUsd": 0.0,
                        "projectedUsd": 0.0,
                        "remainingUsd": max(0.0, config.monthly_budget_usd),
                        "reason": "local Ollama route has no provider API charge",
                    }
                else:
                    raise ValueError(str(decision["reason"]))
        else:
            planned_cost = 0.0
            usage = self.budget.usage_summary(
                at=now.isoformat(), monthly_budget_usd=config.monthly_budget_usd
            )
            decision = {
                "state": "ALLOW",
                "month": usage["month"],
                "spentUsd": usage["spentUsd"],
                "reservedUsd": usage["reservedUsd"],
                "plannedCostUsd": 0.0,
                "projectedUsd": usage["projectedUsd"],
                "remainingUsd": usage["remainingUsd"],
                "reason": "local Ollama route has no provider API charge",
            }
        return {
            "request": request,
            "config": config,
            "pricing": pricing,
            "route": route,
            "responsePlan": plan,
            "style": style,
            "context": context,
            "evidenceIds": evidence_ids,
            "evidenceStats": evidence_stats,
            "estimatedInputTokens": estimated_input_tokens,
            "plannedCostUsd": planned_cost,
            "budget": decision,
            "reservationId": reservation_id,
            "now": now,
        }

    def preview(self, payload: object) -> dict[str, object]:
        prepared = self._prepare(payload, reserve=False)
        route = prepared["route"]
        plan = prepared["responsePlan"]
        style = prepared["style"]
        context = prepared["context"]
        assert isinstance(route, IntelligenceRoute)
        assert isinstance(plan, JobResponsePlan)
        assert isinstance(context, tuple)
        return {
            "state": "READY_FOR_PROVIDER",
            "providerCallMade": False,
            "provider": route.provider,
            "model": route.model,
            "modelLane": route.lane,
            "routeReason": route.reason,
            "responseIntent": plan.intent,
            "styleSamples": style.samples,
            "evidenceIds": [item.evidence_id for item in context],
            "evidenceStats": prepared["evidenceStats"],
            "estimatedInputTokens": prepared["estimatedInputTokens"],
            "plannedCostUsd": prepared["plannedCostUsd"],
            "budget": prepared["budget"],
            "reviewRequired": True,
        }

    @staticmethod
    def _validate_result(
        result: ProviderGenerationResult,
        *,
        evidence_ids: set[str],
        graph: dict[str, object],
        max_words: int | None,
    ) -> None:
        if result.text.strip() and not result.claims:
            raise ValueError("AI draft is missing required claim-to-evidence structure")
        edges = graph.get("edges")
        edge_list = edges if isinstance(edges, list) else []
        for claim in result.claims:
            if not claim.evidence_ids or any(
                item not in evidence_ids for item in claim.evidence_ids
            ):
                raise ValueError("AI draft contains a claim unsupported by the supplied evidence")
            claim_ids = set(claim.evidence_ids)
            if any(
                isinstance(edge, dict)
                and edge.get("relation") == "CONTRADICTS"
                and edge.get("from_evidence_id") in claim_ids
                and edge.get("to_evidence_id") in claim_ids
                for edge in edge_list
            ):
                raise ValueError("AI draft relies on contradictory evidence")
        if max_words is not None and len(result.text.split()) > max_words:
            raise ValueError("AI draft exceeds the requested word limit")

    def generate(self, payload: object) -> dict[str, object]:
        prepared = self._prepare(payload, reserve=True)
        request = prepared["request"]
        config = prepared["config"]
        pricing = prepared["pricing"]
        route = prepared["route"]
        plan = prepared["responsePlan"]
        style = prepared["style"]
        context = prepared["context"]
        evidence_ids = prepared["evidenceIds"]
        reservation_id = prepared["reservationId"]
        now = prepared["now"]
        assert isinstance(request, dict)
        assert isinstance(config, AIConfiguration)
        assert isinstance(route, IntelligenceRoute)
        assert isinstance(plan, JobResponsePlan)
        assert isinstance(context, tuple)
        assert isinstance(evidence_ids, set)
        assert isinstance(now, datetime)
        correlation_id = str(request["correlationId"])
        self.applications.ensure(str(request["applicationId"]), now.isoformat())
        provider_name = route.provider
        model = route.model
        if provider_name == "openai":
            provider = self.provider_factory(self.ai_store.get_api_key())
        else:
            provider = self.ollama_provider_factory()
        try:
            result = provider.generate_structured(
                ProviderGenerationRequest(
                    model=model,
                    question=str(request["question"]),
                    semantic_type=str(request["semanticType"]),
                    context=context,
                    max_words=plan.default_max_words,
                    max_output_tokens=int(request["maxOutputTokens"]),
                    response_intent=plan.intent,
                    style_instructions=style.instructions(),
                )
            )
        except Exception:
            if provider_name == "openai" and isinstance(reservation_id, str):
                estimated_usage_id = f"ai-use-{reservation_id.removeprefix('ai-res-')}"
                self.budget.settle(
                    reservation_id=reservation_id,
                    usage_id=estimated_usage_id,
                    provider="openai",
                    model=model,
                    input_tokens=int(prepared["estimatedInputTokens"]),
                    output_tokens=int(request["maxOutputTokens"]),
                    cost_usd=float(prepared["plannedCostUsd"]),
                    correlation_id=f"{correlation_id}:estimated-provider-failure",
                    at=self._now().isoformat(),
                    estimated=True,
                )
                reservation_id = None
                pricing = None
            if route.fallback_provider == "ollama" and route.fallback_model:
                provider_name = "ollama"
                model = route.fallback_model
                result = self.ollama_provider_factory().generate_structured(
                    ProviderGenerationRequest(
                        model=model,
                        question=str(request["question"]),
                        semantic_type=str(request["semanticType"]),
                        context=context,
                        max_words=plan.default_max_words,
                        max_output_tokens=int(request["maxOutputTokens"]),
                        response_intent=plan.intent,
                        style_instructions=style.instructions(),
                    )
                )
                reservation_id = None
                pricing = None
            else:
                raise
        if provider_name == "openai":
            assert isinstance(pricing, PricingSnapshot)
            assert isinstance(reservation_id, str)
            actual_cost = _cost(pricing, result.usage.input_tokens, result.usage.output_tokens)
            usage_id = f"ai-use-{reservation_id.removeprefix('ai-res-')}"
            self.budget.settle(
                reservation_id=reservation_id,
                usage_id=usage_id,
                provider="openai",
                model=result.model,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                cost_usd=actual_cost,
                correlation_id=correlation_id,
                at=self._now().isoformat(),
                estimated=False,
            )
        else:
            actual_cost = 0.0
            self.architecture.record_ai_usage(
                {
                    "usage_id": f"ai-use-local-{uuid.uuid4()}",
                    "provider": "ollama",
                    "model": result.model,
                    "occurred_at": self._now().isoformat(),
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "cost_usd": 0.0,
                    "correlation_id": correlation_id,
                }
            )
        graph = self.architecture.evidence_graph(str(request["applicationId"]))
        self._validate_result(
            result,
            evidence_ids=evidence_ids,
            graph=graph,
            max_words=plan.default_max_words,
        )
        claims = [
            {"claimId": claim.claim_id, "text": claim.text, "evidenceIds": list(claim.evidence_ids)}
            for claim in result.claims
        ]
        usage = {
            "inputTokens": result.usage.input_tokens,
            "outputTokens": result.usage.output_tokens,
            "totalTokens": result.usage.total_tokens,
            "costUsd": actual_cost,
            "estimated": False,
        }
        draft = self.drafts.create(
            {
                "draftId": f"ai-draft-{uuid.uuid4()}",
                "applicationId": request["applicationId"],
                "pageId": request["pageId"],
                "questionId": request["questionId"],
                "controlId": request["controlId"],
                "question": request["question"],
                "semanticType": request["semanticType"],
                "provider": provider_name,
                "model": result.model,
                "responseId": result.response_id,
                "text": result.text,
                "evidenceIds": sorted(evidence_ids),
                "claims": claims,
                "usage": usage,
                "generatedAt": self._now().isoformat(),
            }
        )
        return {
            "status": "DRAFT_REVIEW_REQUIRED",
            "draftId": draft["draftId"],
            "draft": draft,
            "provider": provider_name,
            "model": result.model,
            "modelLane": plan.model_lane,
            "responseIntent": plan.intent,
            "styleSamples": style.samples,
            "routeReason": route.reason,
            "responseId": result.response_id,
            "text": result.text,
            "claims": claims,
            "evidenceIds": sorted(evidence_ids),
            "usage": usage,
            "budgetState": prepared["budget"]["state"],
            "reviewRequired": True,
            "approved": False,
        }
