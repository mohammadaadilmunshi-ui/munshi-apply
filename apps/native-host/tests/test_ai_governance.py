from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.ai_governance import AIGovernanceService
from munshi_apply_native.ai_settings import AIConfiguration, AISettingsStore
from munshi_apply_native.application_store import ApplicationStore
from munshi_apply_native.architecture_store import ArchitectureStore
from munshi_apply_native.database import Database
from munshi_apply_native.providers import (
    ProviderClaim,
    ProviderGenerationResult,
    ProviderUsage,
)

FIXED_NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    ApplicationStore(database).ensure("app-1", FIXED_NOW.isoformat())
    return database


def configured_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: object
) -> AISettingsStore:
    store = AISettingsStore(tmp_path / "runtime")
    payload: dict[str, object] = {
        "provider": "openai",
        "enabled": True,
        "model": "gpt-5.6-luna",
        "monthlyBudgetUsd": 5,
        "warningBudgetUsd": 4,
        "hardStop": True,
        "allowApplicationDrafts": True,
        "allowProfileEvidence": True,
        "allowResumeEvidence": True,
    }
    payload.update(overrides)
    store.save(AIConfiguration.from_payload(payload))
    monkeypatch.setattr(store, "key_source", lambda: "keychain")
    monkeypatch.setattr(store, "get_api_key", lambda: "test-key-" + ("x" * 40))
    return store


def add_evidence(
    database: Database,
    *,
    evidence_id: str = "ev-1",
    semantic_type: str = "WHY_ROLE",
    text: str = "I have verified recruiting operations and people analytics experience.",
    protected: bool = False,
    trust_level: str = "VERIFIED",
    kind: str = "EMPLOYMENT",
) -> None:
    ArchitectureStore(database).upsert_evidence_node(
        {
            "evidence_id": evidence_id,
            "application_id": "app-1",
            "kind": kind,
            "text": text,
            "semantic_types": [semantic_type],
            "trust_level": trust_level,
            "protected": protected,
            "source": "test-evidence",
            "updated_at": FIXED_NOW.isoformat(),
        }
    )


def request(semantic_type: str = "WHY_ROLE") -> dict[str, object]:
    return {
        "applicationId": "app-1",
        "pageId": "page-1",
        "questionId": "question-1",
        "controlId": "control-1",
        "question": "Why are you interested in this role?",
        "semanticType": semantic_type,
        "correlationId": "question-1",
        "maxWords": 120,
        "maxOutputTokens": 256,
    }


def service(
    database: Database,
    store: AISettingsStore,
    provider_factory: object | None = None,
) -> AIGovernanceService:
    kwargs: dict[str, object] = {"clock": lambda: FIXED_NOW}
    if provider_factory is not None:
        kwargs["provider_factory"] = provider_factory
    return AIGovernanceService(database, store, **kwargs)  # type: ignore[arg-type]


def test_zero_budget_blocks_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch, monthlyBudgetUsd=0, warningBudgetUsd=0)
    add_evidence(database)
    called = False

    def factory(_: str) -> object:
        nonlocal called
        called = True
        raise AssertionError("provider must not be constructed")

    with pytest.raises(ValueError, match="budget is zero"):
        service(database, store, factory).generate(request())
    assert called is False


def test_consequential_question_type_is_never_sent_to_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(database, semantic_type="SPONSORSHIP_FUTURE")
    with pytest.raises(ValueError, match="not eligible"):
        service(database, store).preview(request("SPONSORSHIP_FUTURE"))


def test_protected_or_generated_evidence_cannot_authorize_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(database, protected=True)
    add_evidence(database, evidence_id="ev-generated", trust_level="GENERATED")
    with pytest.raises(ValueError, match="No authoritative non-protected evidence"):
        service(database, store).preview(request())


def test_unresolved_selected_contradiction_blocks_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(
        database, evidence_id="ev-1", text="I prefer this role because of recruiting analytics."
    )
    add_evidence(
        database,
        evidence_id="ev-2",
        text="I prefer this role because I do not want recruiting analytics.",
    )
    ArchitectureStore(database).add_evidence_edge(
        {"from_evidence_id": "ev-1", "to_evidence_id": "ev-2", "relation": "CONTRADICTS"}
    )
    with pytest.raises(ValueError, match="unresolved contradiction"):
        service(database, store).preview(request())


def test_preview_never_calls_provider_or_reserves_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(database)
    result = service(database, store).preview(request())
    assert result["state"] == "READY_FOR_PROVIDER"
    assert result["providerCallMade"] is False
    assert result["reviewRequired"] is True
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM ai_budget_reservations").fetchone()[0]
    assert count == 0


def test_mocked_generation_is_evidence_bound_review_only_and_records_actual_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(database)

    class FakeProvider:
        def generate_structured(self, provider_request: object) -> ProviderGenerationResult:
            return ProviderGenerationResult(
                response_id="resp-test",
                model="gpt-5.6-luna",
                text="My verified recruiting operations experience aligns with this role.",
                claims=(ProviderClaim("claim-1", "Verified recruiting experience", ("ev-1",)),),
                usage=ProviderUsage(input_tokens=100, output_tokens=25, total_tokens=125),
            )

    result = service(database, store, lambda _: FakeProvider()).generate(request())
    assert result["status"] == "DRAFT_REVIEW_REQUIRED"
    assert result["reviewRequired"] is True
    assert result["approved"] is False
    assert result["evidenceIds"] == ["ev-1"]
    assert result["draft"]["status"] == "DRAFT"
    assert result["draft"]["questionId"] == "question-1"
    with database.connect() as connection:
        usage = connection.execute("SELECT * FROM ai_usage").fetchone()
        reservation = connection.execute("SELECT * FROM ai_budget_reservations").fetchone()
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 25
    assert usage["estimated"] == 0
    assert reservation["state"] == "SETTLED"


def test_unsupported_claim_is_rejected_after_usage_is_still_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(database)

    class FakeProvider:
        def generate_structured(self, provider_request: object) -> ProviderGenerationResult:
            return ProviderGenerationResult(
                response_id="resp-test",
                model="gpt-5.6-luna",
                text="Unsupported claim.",
                claims=(ProviderClaim("claim-1", "Unsupported claim", ("unknown-evidence",)),),
                usage=ProviderUsage(input_tokens=50, output_tokens=10, total_tokens=60),
            )

    with pytest.raises(ValueError, match="unsupported"):
        service(database, store, lambda _: FakeProvider()).generate(request())
    with database.connect() as connection:
        usage = connection.execute("SELECT * FROM ai_usage").fetchone()
    assert usage is not None
    assert usage["estimated"] == 0


def test_provider_failure_consumes_conservative_estimated_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(database)

    class FailingProvider:
        def generate_structured(self, provider_request: object) -> ProviderGenerationResult:
            raise ValueError("provider failed")

    with pytest.raises(ValueError, match="provider failed"):
        service(database, store, lambda _: FailingProvider()).generate(request())
    with database.connect() as connection:
        usage = connection.execute("SELECT * FROM ai_usage").fetchone()
        reservation = connection.execute("SELECT * FROM ai_budget_reservations").fetchone()
    assert usage["estimated"] == 1
    assert usage["cost_usd"] > 0
    assert reservation["state"] == "SETTLED"


def test_second_reservation_sees_first_active_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch, monthlyBudgetUsd=0.005, warningBudgetUsd=0)
    add_evidence(database)
    first = service(database, store).preview(request())
    planned = float(first["plannedCostUsd"])
    budget = service(database, store).budget
    one = budget.reserve(
        reservation_id="reservation-one",
        provider="openai",
        model="gpt-5.6-luna",
        correlation_id="one",
        planned_cost_usd=planned,
        monthly_budget_usd=0.005,
        warning_budget_usd=0,
        hard_stop=True,
        at=FIXED_NOW.isoformat(),
    )
    two = budget.reserve(
        reservation_id="reservation-two",
        provider="openai",
        model="gpt-5.6-luna",
        correlation_id="two",
        planned_cost_usd=planned,
        monthly_budget_usd=0.005,
        warning_budget_usd=0,
        hard_stop=True,
        at=FIXED_NOW.isoformat(),
    )
    assert one["state"] == "ALLOW"
    assert two["state"] == "BLOCK"
