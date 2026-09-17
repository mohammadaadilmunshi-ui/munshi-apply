from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.progressive_memory_store import ProgressiveMemoryStore


def create_store(tmp_path: Path) -> ProgressiveMemoryStore:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    return ProgressiveMemoryStore(database)


def memory(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    item: dict[str, object] = {
        "memory_id": "memory-1",
        "memory_kind": "SITE",
        "semantic_type": "COUNTRY",
        "site_origin": "https://jobs.example.test",
        "component_fingerprint": "cfp2-country",
        "question_fingerprint": "question-country",
        "interpretation_key": "location.country",
        "strategy_key": "ARIA_COMBOBOX",
        "canonical_option_key": "country:US",
        "confidence": 0.8,
        "verified_successes": 4,
        "verified_failures": 1,
        "owner_corrections": 0,
        "created_at": now,
        "last_observed_at": now,
        "expires_at": None,
        "version": 1,
        "state": "ACTIVE",
    }
    item.update(overrides)
    return item


def test_memory_round_trip_and_exact_version_progression(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    initial = memory()
    assert store.save_memory(initial) is True
    assert store.save_memory(initial) is False

    updated = {
        **initial,
        "confidence": 0.88,
        "verified_successes": 5,
        "version": 2,
    }
    assert store.save_memory(updated) is True
    saved = store.memory("memory-1")
    assert saved is not None
    assert saved["confidence"] == pytest.approx(0.88)
    assert saved["verified_successes"] == 5
    assert saved["version"] == 2

    with pytest.raises(ValueError, match="exactly one version"):
        store.save_memory({**updated, "version": 4})


def test_memory_identity_cannot_be_redefined(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    initial = memory()
    store.save_memory(initial)

    with pytest.raises(ValueError, match="different definition"):
        store.save_memory(
            {
                **initial,
                "interpretation_key": "citizenship.country",
                "version": 2,
            }
        )


def test_rolled_back_memory_cannot_be_reactivated(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    initial = memory(state="ROLLED_BACK")
    store.save_memory(initial)

    with pytest.raises(ValueError, match="state transition"):
        store.save_memory({**initial, "state": "ACTIVE", "version": 2})


def test_observations_are_append_only_and_idempotent(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    initial = memory()
    store.save_memory(initial)
    observation = {
        "observation_id": "observation-1",
        "memory_id": "memory-1",
        "occurred_at": datetime.now(UTC).isoformat(),
        "success": False,
        "verified": True,
        "owner_corrected": True,
        "failure_class": "OWNER_CORRECTION",
    }

    assert store.record_observation(observation) is True
    assert store.record_observation(observation) is False
    assert store.observations("memory-1") == [observation]


def test_candidate_lookup_keeps_global_and_exact_memory_available(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.save_memory(memory(memory_id="site-memory"))
    store.save_memory(
        memory(
            memory_id="global-memory",
            memory_kind="GLOBAL_PATTERN",
            site_origin=None,
            question_fingerprint=None,
            component_fingerprint=None,
            confidence=0.6,
        )
    )

    candidates = store.candidates(
        semantic_type="COUNTRY",
        site_origin="https://jobs.example.test",
        component_fingerprint="cfp2-country",
        question_fingerprint="question-country",
    )
    assert [candidate["memory_id"] for candidate in candidates] == [
        "site-memory",
        "global-memory",
    ]


def test_global_memory_rejects_site_binding(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    with pytest.raises(ValueError, match="cannot be site/question bound"):
        store.save_memory(memory(memory_kind="GLOBAL_PATTERN"))
