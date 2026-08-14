from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.ai_draft_store import AIDraftStore
from munshi_apply_native.application_store import ApplicationStore
from munshi_apply_native.database import Database

NOW = "2026-08-14T23:00:00+00:00"


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "drafts.sqlite", migrations)
    result.migrate()
    ApplicationStore(result).ensure("app-1", NOW)
    return result


def record(draft_id: str = "draft-1", text: str = "Evidence-backed answer") -> dict[str, object]:
    return {
        "draftId": draft_id,
        "applicationId": "app-1",
        "pageId": "page-1",
        "questionId": "question-1",
        "controlId": "control-1",
        "question": "Why this role?",
        "semanticType": "WHY_ROLE",
        "provider": "openai",
        "model": "gpt-test",
        "responseId": f"response-{draft_id}",
        "text": text,
        "evidenceIds": ["evidence-1"],
        "claims": [{"claimId": "claim-1", "text": text, "evidenceIds": ["evidence-1"]}],
        "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15, "costUsd": 0.001},
        "generatedAt": NOW,
    }


def test_edit_invalidates_approval_and_stale_hash_is_rejected(tmp_path: Path) -> None:
    store = AIDraftStore(database(tmp_path))
    created = store.create(record())
    approved = store.approve(created["draftId"], created["contentSha256"], NOW)
    assert approved["status"] == "APPROVED"

    edited = store.update_text(
        approved["draftId"], "Owner edited answer", approved["contentSha256"], NOW
    )
    assert edited["status"] == "DRAFT"
    assert edited["approvedAt"] is None
    with pytest.raises(ValueError, match="changed"):
        store.approve(edited["draftId"], approved["contentSha256"], NOW)


def test_regeneration_supersedes_previous_current_draft(tmp_path: Path) -> None:
    store = AIDraftStore(database(tmp_path))
    first = store.create(record("draft-1"))
    first = store.approve(first["draftId"], first["contentSha256"], NOW)
    second = store.create(record("draft-2", "New answer"))
    rows = store.list_for_application("app-1", "page-1")
    statuses = {row["draftId"]: row["status"] for row in rows}
    assert statuses[first["draftId"]] == "SUPERSEDED"
    assert statuses[second["draftId"]] == "DRAFT"


def test_only_approved_draft_can_be_marked_used(tmp_path: Path) -> None:
    store = AIDraftStore(database(tmp_path))
    created = store.create(record())
    with pytest.raises(ValueError, match="approved"):
        store.mark_used(created["draftId"], NOW)
    approved = store.approve(created["draftId"], created["contentSha256"], NOW)
    used = store.mark_used(approved["draftId"], NOW)
    assert used["status"] == "USED"
    assert used["usedAt"] is not None


def test_rejected_draft_cannot_be_edited_or_approved(tmp_path: Path) -> None:
    store = AIDraftStore(database(tmp_path))
    created = store.create(record())
    rejected = store.reject(created["draftId"], NOW)
    assert rejected["status"] == "REJECTED"
    with pytest.raises(ValueError, match="no longer"):
        store.update_text(rejected["draftId"], "Changed", rejected["contentSha256"], NOW)
    with pytest.raises(ValueError, match="current draft"):
        store.approve(rejected["draftId"], rejected["contentSha256"], NOW)
