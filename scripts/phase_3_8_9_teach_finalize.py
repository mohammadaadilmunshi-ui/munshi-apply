from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:90]!r}")
    write(path, content.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    content = read(path)
    next_content, count = re.subn(pattern, replacement, content, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{path}: regex expected one match: {pattern[:100]!r}")
    write(path, next_content)


replace_once(
    "apps/extension/public/manifest.json",
    '"version": "0.2.4"',
    '"version": "0.2.5"',
)

replace_once(
    "apps/native-host/src/munshi_apply_native/ai_draft_store.py",
    """        return self._wire(row)\n\n    def list_for_application(""",
    """        return self._wire(row)\n\n    def get(self, draft_id: str) -> dict[str, object]:\n        draft_id = _required(draft_id, \"draftId\")\n        with self.database.connect() as connection:\n            row = connection.execute(\n                \"SELECT * FROM ai_drafts WHERE draft_id = ?\", (draft_id,)\n            ).fetchone()\n        return self._wire(row)\n\n    def list_for_application(""",
)

path = "apps/native-host/src/munshi_apply_native/ai_governance.py"
content = read(path)
content = content.replace(
    """from .providers import (\n    OpenAIResponsesProvider,\n    ProviderContextItem,\n    ProviderGenerationRequest,\n    ProviderGenerationResult,\n)""",
    """from .intelligence_router import IntelligenceRoute, choose_intelligence_route\nfrom .providers import (\n    OllamaChatProvider,\n    OpenAIResponsesProvider,\n    ProviderContextItem,\n    ProviderGenerationRequest,\n    ProviderGenerationResult,\n)\nfrom .response_planner import JobResponsePlan, plan_job_response\nfrom .writing_style import WritingStyleStore""",
)
content = content.replace("_MAX_CONTEXT_ITEMS = 5", "_MAX_CONTEXT_ITEMS = 7")
content = content.replace("_MAX_CONTEXT_CHARACTERS = 6_000", "_MAX_CONTEXT_CHARACTERS = 8_000")
content = content.replace(
    '        "BEHAVIORAL_EXAMPLE",\n',
    '        "BEHAVIORAL_EXAMPLE",\n        "ROLE_RESPONSIBILITIES",\n        "ROLE_UNDERSTANDING",\n        "MOTIVATION",\n        "RECRUITMENT_MOTIVATION",\n',
    1,
)
content = content.replace(
    """ProviderFactory = Callable[[str], OpenAIResponsesProvider]\nClock = Callable[[], datetime]\n\n\ndef _default_provider_factory(api_key: str) -> OpenAIResponsesProvider:\n    return OpenAIResponsesProvider(api_key)\n""",
    """ProviderFactory = Callable[[str], OpenAIResponsesProvider]\nOllamaProviderFactory = Callable[[], OllamaChatProvider]\nClock = Callable[[], datetime]\n\n\ndef _default_provider_factory(api_key: str) -> OpenAIResponsesProvider:\n    return OpenAIResponsesProvider(api_key)\n\n\ndef _default_ollama_provider_factory() -> OllamaChatProvider:\n    return OllamaChatProvider()\n""",
)
content = content.replace(
    """        provider_factory: ProviderFactory = _default_provider_factory,\n        clock: Clock = _default_clock,\n    ) -> None:\n        self.database = database\n        self.ai_store = ai_store\n        self.provider_factory = provider_factory\n        self.clock = clock\n""",
    """        provider_factory: ProviderFactory = _default_provider_factory,\n        ollama_provider_factory: OllamaProviderFactory = _default_ollama_provider_factory,\n        clock: Clock = _default_clock,\n    ) -> None:\n        self.database = database\n        self.ai_store = ai_store\n        self.provider_factory = provider_factory\n        self.ollama_provider_factory = ollama_provider_factory\n        self.clock = clock\n""",
)
content = content.replace(
    """        query_tokens = _words(question)""",
    """        retrieval_terms = getattr(self, \"_active_retrieval_terms\", ())\n        query_tokens = _words(question + \" \" + \" \".join(retrieval_terms))""",
    1,
)
content = content.replace(
    """        selected: list[ProviderContextItem] = []\n        selected_ids: set[str] = set()\n        characters = 0\n        for _, node in candidates:""",
    """        selected: list[ProviderContextItem] = []\n        selected_ids: set[str] = set()\n        selected_texts: set[str] = set()\n        source_counts: dict[str, int] = {}\n        characters = 0\n        for _, node in candidates:""",
    1,
)
content = content.replace(
    """            source = str(node.get(\"source\", \"\")).strip()\n            trust = str(node.get(\"trust_level\", \"\")).strip()\n            if not evidence_id or not source or not trust:\n                continue\n            selected.append(ProviderContextItem(evidence_id, source, text, trust))""",
    """            source = str(node.get(\"source\", \"\")).strip()\n            trust = str(node.get(\"trust_level\", \"\")).strip()\n            normalized_text = \" \".join(text.lower().split())\n            if not evidence_id or not source or not trust or normalized_text in selected_texts:\n                continue\n            if source_counts.get(source, 0) >= 3:\n                continue\n            selected.append(ProviderContextItem(evidence_id, source, text, trust))\n            selected_texts.add(normalized_text)\n            source_counts[source] = source_counts.get(source, 0) + 1""",
    1,
)

prepare = '''    def _prepare(self, payload: object, *, reserve: bool) -> dict[str, object]:
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
        if semantic_type not in _SAFE_DRAFT_SEMANTIC_TYPES and plan.intent == "OTHER_NARRATIVE":
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
            raise ValueError("This response needs job/company context; open the job listing in this tab first")
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
                        "spentUsd": self.budget.usage_summary(at=now.isoformat(), monthly_budget_usd=config.monthly_budget_usd)["spentUsd"],
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
            usage = self.budget.usage_summary(at=now.isoformat(), monthly_budget_usd=config.monthly_budget_usd)
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

'''
content, count = re.subn(r"    def _prepare\(.*?(?=    def preview\()", prepare, content, count=1, flags=re.S)
if count != 1:
    raise RuntimeError("ai_governance.py: could not replace _prepare")

preview = '''    def preview(self, payload: object) -> dict[str, object]:
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

'''
content, count = re.subn(r"    def preview\(.*?(?=    @staticmethod\n    def _validate_result)", preview, content, count=1, flags=re.S)
if count != 1:
    raise RuntimeError("ai_governance.py: could not replace preview")

generate = '''    def generate(self, payload: object) -> dict[str, object]:
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
                self.budget.release(reservation_id, at=self._now().isoformat())
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
'''
content, count = re.subn(r"    def generate\(.*\Z", generate, content, count=1, flags=re.S)
if count != 1:
    raise RuntimeError("ai_governance.py: could not replace generate")
write(path, content)

path = "apps/extension/src/messaging/client.ts"
content = read(path)
content = content.replace(
    """    ai_draft_lifecycle?: boolean;\n""",
    """    ai_draft_lifecycle?: boolean;\n    document_evidence_ingestion?: boolean;\n    provider_routing?: boolean;\n    ollama_fallback?: boolean;\n    writing_style_learning?: boolean;\n    teach_munshi_state_capture?: boolean;\n""",
    1,
)
content = content.replace("export const REQUIRED_NATIVE_PROTOCOL_VERSION = 2;", "export const REQUIRED_NATIVE_PROTOCOL_VERSION = 3;")
content = content.replace(
    '    "ai_draft_lifecycle",\n',
    '    "ai_draft_lifecycle",\n    "document_evidence_ingestion",\n    "provider_routing",\n    "writing_style_learning",\n',
    1,
)
content = content.replace(
    """  eventTypes: string[];\n  recipe: null | {""",
    """  eventTypes: string[];\n  eventSequence?: { type: string; target: string; atMs: number }[];\n  beforeState?: Record<string, unknown>;\n  afterState?: Record<string, unknown>;\n  quality?: { score: number; reasons: string[]; valueCommitted: boolean };\n  recipe: null | {""",
    1,
)
write(path, content)

path = "apps/extension/src/content/teach.ts"
content = read(path)
content = content.replace(
    """export type TeachInteractionCapture = {\n  sessionId: string;\n  controlId: string;\n  componentFingerprint: string;\n  changed: boolean;\n  reusable: boolean;\n  actions: RecipeAction[];\n  eventTypes: string[];\n  startedAt: string;\n  finishedAt: string;\n};""",
    """export type TeachInteractionCapture = {\n  sessionId: string;\n  controlId: string;\n  componentFingerprint: string;\n  changed: boolean;\n  reusable: boolean;\n  actions: RecipeAction[];\n  eventTypes: string[];\n  eventSequence: { type: string; target: string; atMs: number }[];\n  beforeState: Record<string, unknown>;\n  afterState: Record<string, unknown>;\n  quality: { score: number; reasons: string[]; valueCommitted: boolean };\n  startedAt: string;\n  finishedAt: string;\n};""",
)
content = content.replace(
    """  eventTypes: Set<string>;\n  abortController: AbortController;\n};""",
    """  eventTypes: Set<string>;\n  eventSequence: { type: string; target: string; atMs: number }[];\n  startedAtMs: number;\n  abortController: AbortController;\n};""",
)
content = content.replace(
    """function marker(element: HTMLElement): string {""",
    """function stateFor(element: HTMLElement): Record<string, unknown> {\n  const input = element instanceof HTMLInputElement ? element : null;\n  const select = element instanceof HTMLSelectElement ? element : null;\n  const textarea = element instanceof HTMLTextAreaElement ? element : null;\n  return {\n    value: input?.value ?? select?.value ?? textarea?.value ?? element.textContent ?? \"\",\n    checked: input?.checked ?? element.getAttribute(\"aria-checked\"),\n    selected: element.getAttribute(\"aria-selected\"),\n    expanded: element.getAttribute(\"aria-expanded\"),\n    invalid: element.getAttribute(\"aria-invalid\"),\n    disabled: input?.disabled ?? select?.disabled ?? textarea?.disabled ?? element.getAttribute(\"aria-disabled\"),\n    role: element.getAttribute(\"role\"),\n  };\n}\n\nfunction marker(element: HTMLElement): string {""",
    1,
)
content = content.replace(
    """  return JSON.stringify({\n    checked: input?.checked ?? element.getAttribute(\"aria-checked\"),\n    selected: element.getAttribute(\"aria-selected\"),\n    expanded: element.getAttribute(\"aria-expanded\"),\n    value:\n      input?.value ??\n      select?.value ??\n      textarea?.value ??\n      element.textContent ??\n      \"\",\n  });""",
    """  void input;\n  void select;\n  void textarea;\n  return JSON.stringify(stateFor(element));""",
    1,
)
content = content.replace(
    """  const eventTypes = new Set<string>();\n  const options = { capture: true, signal: abortController.signal } as const;""",
    """  const eventTypes = new Set<string>();\n  const eventSequence: { type: string; target: string; atMs: number }[] = [];\n  const startedAtMs = performance.now();\n  const options = { capture: true, signal: abortController.signal } as const;""",
    1,
)
content = content.replace(
    """      (event) => {\n        if (eventName === \"keydown\" && event instanceof KeyboardEvent) {""",
    """      (event) => {\n        const target = event.target instanceof Element ? event.target : null;\n        const related = target === element || Boolean(target && (element.contains(target) || target.closest(`[aria-controls=\\\"${element.id}\\\"]`)));\n        if (!related && ![\"keydown\", \"focus\", \"blur\"].includes(eventName)) return;\n        if (eventName === \"keydown\" && event instanceof KeyboardEvent) {""",
    1,
)
content = content.replace(
    """          eventTypes.add(`key:${event.key}`);\n          return;\n        }\n        eventTypes.add(eventName);""",
    """          eventTypes.add(`key:${event.key}`);\n          eventSequence.push({ type: `key:${event.key}`, target: related ? \"control\" : \"document\", atMs: Math.round(performance.now() - startedAtMs) });\n          return;\n        }\n        eventTypes.add(eventName);\n        eventSequence.push({ type: eventName, target: related ? \"control\" : \"document\", atMs: Math.round(performance.now() - startedAtMs) });""",
    1,
)
content = content.replace(
    """    eventTypes,\n    abortController,""",
    """    eventTypes,\n    eventSequence,\n    startedAtMs,\n    abortController,""",
    1,
)
content = content.replace(
    """  const actions = inferredActions(current.element, current.eventTypes);\n  const changed =\n    current.beforeMarker !== marker(current.element) ||\n    current.eventTypes.has(\"input\") ||\n    current.eventTypes.has(\"change\") ||\n    current.eventTypes.has(\"click\");\n  const result: TeachInteractionCapture = {""",
    """  const actions = inferredActions(current.element, current.eventTypes);\n  const afterMarker = marker(current.element);\n  const changed = current.beforeMarker !== afterMarker;\n  const beforeState = JSON.parse(current.beforeMarker) as Record<string, unknown>;\n  const afterState = JSON.parse(afterMarker) as Record<string, unknown>;\n  const valueCommitted = changed && (current.eventTypes.has(\"change\") || current.eventTypes.has(\"input\") || current.eventTypes.has(\"click\"));\n  const reasons: string[] = [];\n  if (changed) reasons.push(\"control-state-changed\");\n  if (valueCommitted) reasons.push(\"value-commit-observed\");\n  if (current.eventSequence.some((item) => item.target === \"control\")) reasons.push(\"targeted-events-observed\");\n  const score = Math.min(1, (changed ? 0.5 : 0) + (valueCommitted ? 0.3 : 0) + (reasons.includes(\"targeted-events-observed\") ? 0.2 : 0));\n  const result: TeachInteractionCapture = {""",
    1,
)
content = content.replace(
    """    changed,\n    reusable: changed && actions.length > 0,\n    actions,\n    eventTypes: [...current.eventTypes],""",
    """    changed,\n    reusable: score >= 0.8 && actions.length > 0,\n    actions,\n    eventTypes: [...current.eventTypes],\n    eventSequence: current.eventSequence.slice(0, 60),\n    beforeState,\n    afterState,\n    quality: { score, reasons, valueCommitted },""",
    1,
)
write(path, content)

path = "apps/extension/src/background/service-worker.ts"
content = read(path)
content = content.replace(
    """          finishedAt: string;\n        };""",
    """          finishedAt: string;\n          eventSequence?: { type: string; target: string; atMs: number }[];\n          beforeState?: Record<string, unknown>;\n          afterState?: Record<string, unknown>;\n          quality?: { score: number; reasons: string[]; valueCommitted: boolean };\n        };""",
    1,
)
content = content.replace(
    """  if (!capture.reusable) return { ...capture, recipe: null };""",
    """  if (!capture.reusable || (capture.quality?.score ?? 0) < 0.8)\n    return { ...capture, recipe: null };""",
    1,
)
write(path, content)

path = "apps/extension/src/sidepanel/TeachMunshiPanel.tsx"
content = read(path)
content = content.replace(
    """      setMessage(\n        `Candidate recipe v${learned.recipe.version} saved in ${learned.recipe.state.toLowerCase()} mode. MUNSHI will try it on the matching control and promote it after verified success.`,\n      );""",
    """      const quality = learned.quality ? ` · capture ${Math.round(learned.quality.score * 100)}%` : \"\";\n      setMessage(\n        `Candidate recipe v${learned.recipe.version} saved in ${learned.recipe.state.toLowerCase()} mode${quality}. MUNSHI will try it on the matching control and promote it after verified success.`,\n      );""",
    1,
)
content = content.replace(
    """          \"MUNSHI observed the interaction but could not infer a reusable safe recipe. You can continue manually; the application was not blocked.\",\n""",
    """          learned.quality\n            ? `MUNSHI observed the interaction, but capture quality was ${Math.round(learned.quality.score * 100)}%. Retry the one control slowly so its committed before/after state is visible; the application remains unblocked.`\n            : \"MUNSHI observed the interaction but could not infer a reusable safe recipe. You can continue manually; the application was not blocked.\",\n""",
    1,
)
write(path, content)

write(
    "apps/native-host/tests/test_response_planner.py",
    '''from munshi_apply_native.response_planner import classify_response_intent, plan_job_response\n\n\ndef test_job_specific_intents_and_model_lanes():\n    assert classify_response_intent("Why do you want to join our company?", "WHY_COMPANY") == "WHY_COMPANY"\n    assert plan_job_response("Tell us about a time you solved a hard problem", "BEHAVIORAL_EXAMPLE").model_lane == "STRONG"\n    plan = plan_job_response("Why this role?", "WHY_ROLE")\n    assert plan.requires_job_context is True\n    assert plan.requires_candidate_evidence is True\n''',
)

write(
    "apps/native-host/tests/test_resume_parser.py",
    '''import io\nimport zipfile\n\nimport pytest\n\nfrom munshi_apply_native.resume_parser import parse_resume_bytes, resume_evidence_nodes\n\n\ndef docx_bytes(text: str) -> bytes:\n    buffer = io.BytesIO()\n    with zipfile.ZipFile(buffer, "w") as archive:\n        archive.writestr("word/document.xml", f'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')\n    return buffer.getvalue()\n\n\ndef test_docx_resume_becomes_stable_evidence_chunks():\n    parsed = parse_resume_bytes("resume.docx", docx_bytes("Recruiting experience improved onboarding results with analytics and Excel dashboards."))\n    nodes = resume_evidence_nodes(resume_id="r1", resume_sha256="a" * 64, parsed=parsed, application_id=None, updated_at="2026-08-17T00:00:00+00:00")\n    assert parsed.parser == "docx-xml"\n    assert nodes\n    assert nodes[0]["trust_level"] == "DOCUMENT_CONFIRMED"\n    assert "RELEVANT_EXPERIENCE" in nodes[0]["semantic_types"]\n\n\ndef test_legacy_doc_is_explicitly_not_silently_parsed():\n    with pytest.raises(ValueError, match="convert it to PDF or DOCX"):\n        parse_resume_bytes("resume.doc", b"not-a-modern-doc")\n''',
)

write(
    "apps/native-host/tests/test_writing_style.py",
    '''from munshi_apply_native.writing_style import WritingStyleStore\n\n\ndef test_style_learning_only_uses_approved_owner_edit(tmp_path):\n    store = WritingStyleStore(tmp_path)\n    unchanged = store.learn_from_approved_edit("Generated answer", "Generated answer")\n    assert unchanged.samples == 0\n    learned = store.learn_from_approved_edit(\n        "I am extremely excited to leverage my extensive background in this wonderful opportunity.",\n        "I’m interested because the role connects recruiting operations with analytics, which matches my experience.",\n    )\n    assert learned.samples == 1\n    assert "learned style" in learned.instructions().lower()\n''',
)

write(
    "packages/application-model/src/job-response.test.ts",
    '''import { describe, expect, it } from "vitest";\nimport { classifyJobResponseIntent, planJobResponse } from "./job-response";\n\ndescribe("job response planning", () => {\n  it("uses strong reasoning for behavioral and transition answers", () => {\n    expect(classifyJobResponseIntent("Tell us about a time you handled a difficult stakeholder", "BEHAVIORAL_EXAMPLE")).toBe("BEHAVIORAL");\n    expect(planJobResponse("Why are you leaving your current employer?", "CAREER_GOALS").modelLane).toBe("STRONG");\n  });\n  it("requires both job and candidate evidence for why-role", () => {\n    const plan = planJobResponse("Why this role?", "WHY_ROLE");\n    expect(plan.requiresJobContext).toBe(true);\n    expect(plan.requiresCandidateEvidence).toBe(true);\n  });\n});\n''',
)

write(
    "packages/application-model/src/retrieval.test.ts",
    '''import { describe, expect, it } from "vitest";\nimport { retrieveEvidenceHybrid } from "./retrieval";\nimport { planJobResponse } from "./job-response";\nimport type { EvidenceGraph } from "./evidence";\n\ndescribe("hybrid evidence retrieval", () => {\n  it("brings job context and candidate evidence into a why-role context without protected/generated evidence", () => {\n    const graph: EvidenceGraph = {\n      nodes: [\n        { evidenceId: "job", kind: "JOB_REQUIREMENT", text: "Coordinate consultant recruiting and candidate operations", semanticTypes: ["WHY_ROLE"], trustLevel: "DOCUMENT_CONFIRMED", protected: false, source: "job-listing", updatedAt: "2026-08-17T00:00:00Z" },\n        { evidenceId: "resume", kind: "RESUME_BULLET", text: "Recruiting operations experience with onboarding and candidate coordination", semanticTypes: ["RELEVANT_EXPERIENCE"], trustLevel: "DOCUMENT_CONFIRMED", protected: false, source: "resume:r1", updatedAt: "2026-08-17T00:00:00Z" },\n        { evidenceId: "secret", kind: "PROFILE_FACT", text: "protected fact", semanticTypes: ["WHY_ROLE"], trustLevel: "VERIFIED", protected: true, source: "profile", updatedAt: "2026-08-17T00:00:00Z" },\n      ],\n      edges: [],\n    };\n    const hits = retrieveEvidenceHybrid(graph, { query: "Why this recruiting role?", semanticType: "WHY_ROLE", plan: planJobResponse("Why this role?", "WHY_ROLE") });\n    expect(hits.map((item) => item.node.evidenceId)).toContain("job");\n    expect(hits.map((item) => item.node.evidenceId)).toContain("resume");\n    expect(hits.map((item) => item.node.evidenceId)).not.toContain("secret");\n  });\n});\n''',
)

write(
    "docs/reports/PHASE_3_8_9_AND_TEACH_STRENGTHENING_2026-08-17.md",
    '''# MUNSHI Apply — Phase 3, Phase 8, Phase 9 + Teach-MUNSHI strengthening\n\n**Build mode:** source/CI only; owner-side deployment intentionally deferred.\n\n## Phase 3 — Evidence & Retrieval\n\n- Durable Evidence Graph remains the authority.\n- Added PDF/DOCX/TXT/MD résumé parsing with explicit refusal for legacy `.doc` and image-only/no-text files rather than false parsing.\n- Added resumable, SHA-256-verified Native Messaging document ingestion so original résumé bytes can be indexed without putting large documents into a single native message.\n- Résumé evidence is chunked, source-bound, `DOCUMENT_CONFIRMED`, non-protected by default, and replaces older indexed chunks for the same résumé identity.\n- Added hybrid semantic retrieval planning with trust, evidence kind, semantic intent, query overlap, source diversity, duplicate suppression, and contradiction avoidance.\n- Job-specific context assembly expands retrieval using the response intent rather than only literal question words.\n\n## Phase 8 — Provider-Agnostic Intelligence\n\n- OpenAI remains supported through the Responses API adapter.\n- Added a provider interface and local Ollama structured-output adapter using a loopback-only endpoint.\n- Added cheap/strong model lanes and response-intent routing.\n- Added `auto`, `openai`, and `ollama` provider policies with optional local fallback.\n- Paid OpenAI routes retain pricing/budget reservation enforcement; local Ollama routes have zero provider API cost and do not consume the paid budget.\n- A blocked paid route can select configured local fallback rather than making the application question unusable.\n\n## Phase 9 — Job-Specific Responses\n\n- Added intent planning for Why Company, Why Role, role understanding, relevant experience, career transition, motivation, behavioral, and other narrative questions.\n- Intent controls evidence requirements, retrieval vocabulary, default answer length, and cheap/strong model lane.\n- Job/company-dependent answers require captured job context instead of generic guessing.\n- Existing claim-to-evidence validation, contradiction checking, exact owner approval, and word limits remain enforced.\n- Added writing-style learning from owner-edited answers only when the exact edit is approved. Rejected or untouched generated drafts do not train the preference profile.\n\n## Teach-MUNSHI strengthening\n\n- Demonstrations now capture structured before/after control state, a bounded event sequence, targeted-event evidence, commit evidence, and a capture quality score.\n- Unrelated page clicks no longer make a demonstration reusable.\n- A recipe requires a real control-state change plus commit evidence and high capture quality before it is saved.\n- Existing value-free recipes, SHADOW testing, promotion, versioning, verification, fallback, and rollback remain intact.\n\n## Practical principle\n\nTruth/security boundaries remain hard boundaries. Missing job context, unsupported document formats, unverified provider output, and low-quality demonstrations are surfaced clearly. Routine application work should otherwise keep moving through deterministic retrieval, local/cloud model routing, owner review, and recoverable teaching.\n''',
)
