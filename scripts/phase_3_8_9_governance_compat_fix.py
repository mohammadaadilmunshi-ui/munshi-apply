from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:110]!r}")
    write(path, content.replace(old, new, 1))


replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    '''        if semantic_type not in _SAFE_DRAFT_SEMANTIC_TYPES and plan.intent == "OTHER_NARRATIVE":
            raise ValueError("This application question type is not eligible for AI generation")''',
    '''        if semantic_type not in _SAFE_DRAFT_SEMANTIC_TYPES:
            raise ValueError("This application question type is not eligible for AI generation")''',
)

replace_once(
    "apps/native-host/src/munshi_apply_native/ai_governance.py",
    '''        except Exception:
            if provider_name == "openai" and isinstance(reservation_id, str):
                self.budget.release(reservation_id, at=self._now().isoformat())
            if route.fallback_provider == "ollama" and route.fallback_model:
                provider_name = "ollama"
                model = route.fallback_model
                result = self.ollama_provider_factory().generate_structured(''',
    '''        except Exception:
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
                result = self.ollama_provider_factory().generate_structured(''',
)

replace_once(
    "apps/native-host/tests/test_ai_governance.py",
    '            "source": "test-evidence",',
    '            "source": "job-listing",',
)
replace_once(
    "apps/native-host/tests/test_native_ai_governance_messages.py",
    '            "source": "test",',
    '            "source": "job-listing",',
)
replace_once(
    "apps/native-host/tests/test_native_messaging.py",
    '    assert data["protocol_version"] == 2',
    '    assert data["protocol_version"] == 3',
)
replace_once(
    "apps/native-host/tests/test_native_messaging.py",
    '    assert data["capabilities"]["profile_vault"] is True',
    '''    assert data["capabilities"]["profile_vault"] is True
    assert data["capabilities"]["document_evidence_ingestion"] is True
    assert data["capabilities"]["provider_routing"] is True
    assert data["capabilities"]["writing_style_learning"] is True
    assert data["capabilities"]["teach_munshi_state_capture"] is True''',
)

append = '''

def test_why_role_requires_job_context_even_when_candidate_evidence_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    ArchitectureStore(database).upsert_evidence_node(
        {
            "evidence_id": "candidate-only",
            "application_id": "app-1",
            "kind": "EMPLOYMENT",
            "text": "Verified recruiting operations experience",
            "semantic_types": ["WHY_ROLE"],
            "trust_level": "VERIFIED",
            "protected": False,
            "source": "profile",
            "updated_at": FIXED_NOW.isoformat(),
        }
    )
    with pytest.raises(ValueError, match="job/company context"):
        service(database, store).preview(request())


def test_consequential_semantic_type_cannot_be_overridden_by_why_role_wording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = create_database(tmp_path)
    store = configured_store(tmp_path, monkeypatch)
    add_evidence(database, semantic_type="SPONSORSHIP_FUTURE")
    payload = request("SPONSORSHIP_FUTURE")
    payload["question"] = "Why this role, and will you require sponsorship in the future?"
    with pytest.raises(ValueError, match="not eligible"):
        service(database, store).preview(payload)
'''
path = "apps/native-host/tests/test_ai_governance.py"
content = read(path)
if "test_why_role_requires_job_context_even_when_candidate_evidence_exists" not in content:
    content += append
write(path, content)
