from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from .database import Database

_ALLOWED_STATUSES = {"DRAFT", "APPROVED", "REJECTED", "SUPERSEDED", "USED"}


def _required(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: object, name: str) -> str:
    text = _required(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprint(record: dict[str, object]) -> str:
    canonical = "\n".join(
        [
            _required(record.get("applicationId"), "applicationId"),
            _required(record.get("pageId"), "pageId"),
            _required(record.get("questionId"), "questionId"),
            _required(record.get("controlId"), "controlId"),
            _required(record.get("question"), "question"),
            _required(record.get("semanticType"), "semanticType"),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AIDraftStore:
    """Durable owner-review lifecycle for generated application answers."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _wire(row: object) -> dict[str, object]:
        if row is None:
            raise KeyError("AI draft does not exist")
        data = dict(row)
        status = str(data["status"])
        if status not in _ALLOWED_STATUSES:
            raise ValueError("Stored AI draft status is invalid")
        return {
            "draftId": data["draft_id"],
            "applicationId": data["application_id"],
            "pageId": data["page_id"],
            "questionId": data["question_id"],
            "controlId": data["control_id"],
            "questionFingerprint": data["question_fingerprint"],
            "semanticType": data["semantic_type"],
            "provider": data["provider"],
            "model": data["model"],
            "responseId": data["response_id"],
            "originalText": data["original_text"],
            "currentText": data["current_text"],
            "contentSha256": data["content_sha256"],
            "status": status,
            "evidenceIds": json.loads(str(data["evidence_ids_json"])),
            "claims": json.loads(str(data["claims_json"])),
            "usage": json.loads(str(data["usage_json"])),
            "generatedAt": data["generated_at"],
            "updatedAt": data["updated_at"],
            "approvedAt": data["approved_at"],
            "usedAt": data["used_at"],
        }

    def create(self, record: dict[str, object]) -> dict[str, object]:
        draft_id = _required(record.get("draftId"), "draftId")
        application_id = _required(record.get("applicationId"), "applicationId")
        page_id = _required(record.get("pageId"), "pageId")
        question_id = _required(record.get("questionId"), "questionId")
        control_id = _required(record.get("controlId"), "controlId")
        semantic_type = _required(record.get("semanticType"), "semanticType")
        provider = _required(record.get("provider"), "provider")
        model = _required(record.get("model"), "model")
        response_id = _required(record.get("responseId"), "responseId")
        text = _required(record.get("text"), "text")
        generated_at = _timestamp(record.get("generatedAt"), "generatedAt")
        evidence_ids = record.get("evidenceIds")
        claims = record.get("claims")
        usage = record.get("usage")
        if not isinstance(evidence_ids, list) or not all(
            isinstance(item, str) and item.strip() for item in evidence_ids
        ):
            raise ValueError("evidenceIds must be a non-empty-string array")
        if not isinstance(claims, list):
            raise ValueError("claims must be an array")
        if not isinstance(usage, dict):
            raise ValueError("usage must be an object")
        question_fingerprint = _fingerprint(record)
        content_sha256 = _sha256(text)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE ai_drafts
                SET status = 'SUPERSEDED', updated_at = ?
                WHERE application_id = ? AND question_id = ? AND control_id = ?
                  AND status IN ('DRAFT', 'APPROVED')
                """,
                (generated_at, application_id, question_id, control_id),
            )
            connection.execute(
                """
                INSERT INTO ai_drafts (
                    draft_id, application_id, page_id, question_id, control_id,
                    question_fingerprint, semantic_type, provider, model, response_id,
                    original_text, current_text, content_sha256, status,
                    evidence_ids_json, claims_json, usage_json, generated_at,
                    updated_at, approved_at, used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    draft_id,
                    application_id,
                    page_id,
                    question_id,
                    control_id,
                    question_fingerprint,
                    semantic_type,
                    provider,
                    model,
                    response_id,
                    text,
                    text,
                    content_sha256,
                    json.dumps(evidence_ids, separators=(",", ":")),
                    json.dumps(claims, separators=(",", ":")),
                    json.dumps(usage, separators=(",", ":")),
                    generated_at,
                    generated_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ai_drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
            connection.commit()
        return self._wire(row)

    def list_for_application(
        self, application_id: str, page_id: str | None = None
    ) -> list[dict[str, object]]:
        application_id = _required(application_id, "applicationId")
        with self.database.connect() as connection:
            if page_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM ai_drafts
                    WHERE application_id = ?
                    ORDER BY generated_at DESC, draft_id DESC
                    """,
                    (application_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM ai_drafts
                    WHERE application_id = ? AND page_id = ?
                    ORDER BY generated_at DESC, draft_id DESC
                    """,
                    (application_id, _required(page_id, "pageId")),
                ).fetchall()
        return [self._wire(row) for row in rows]

    def _load_for_update(self, connection: object, draft_id: str) -> object:
        row = connection.execute(
            "SELECT * FROM ai_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        if row is None:
            raise KeyError("AI draft does not exist")
        return row

    def update_text(
        self, draft_id: str, text: str, expected_sha256: str, updated_at: str
    ) -> dict[str, object]:
        draft_id = _required(draft_id, "draftId")
        text = _required(text, "text")
        expected_sha256 = _required(expected_sha256, "expectedSha256")
        updated_at = _timestamp(updated_at, "updatedAt")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_for_update(connection, draft_id)
            if row["content_sha256"] != expected_sha256:
                raise ValueError("AI draft changed; refresh before editing")
            if row["status"] in {"REJECTED", "SUPERSEDED", "USED"}:
                raise ValueError("This AI draft can no longer be edited")
            content_sha256 = _sha256(text)
            connection.execute(
                """
                UPDATE ai_drafts
                SET current_text = ?, content_sha256 = ?, status = 'DRAFT',
                    approved_at = NULL, updated_at = ?
                WHERE draft_id = ?
                """,
                (text, content_sha256, updated_at, draft_id),
            )
            row = self._load_for_update(connection, draft_id)
            connection.commit()
        return self._wire(row)

    def approve(
        self, draft_id: str, expected_sha256: str, approved_at: str
    ) -> dict[str, object]:
        draft_id = _required(draft_id, "draftId")
        expected_sha256 = _required(expected_sha256, "expectedSha256")
        approved_at = _timestamp(approved_at, "approvedAt")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_for_update(connection, draft_id)
            if row["content_sha256"] != expected_sha256:
                raise ValueError("AI draft changed; refresh before approving")
            if row["status"] != "DRAFT":
                raise ValueError("Only a current draft can be approved")
            connection.execute(
                """
                UPDATE ai_drafts
                SET status = 'APPROVED', approved_at = ?, updated_at = ?
                WHERE draft_id = ?
                """,
                (approved_at, approved_at, draft_id),
            )
            row = self._load_for_update(connection, draft_id)
            connection.commit()
        return self._wire(row)

    def reject(self, draft_id: str, rejected_at: str) -> dict[str, object]:
        draft_id = _required(draft_id, "draftId")
        rejected_at = _timestamp(rejected_at, "rejectedAt")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_for_update(connection, draft_id)
            if row["status"] not in {"DRAFT", "APPROVED"}:
                raise ValueError("This AI draft can no longer be rejected")
            connection.execute(
                """
                UPDATE ai_drafts
                SET status = 'REJECTED', approved_at = NULL, updated_at = ?
                WHERE draft_id = ?
                """,
                (rejected_at, draft_id),
            )
            row = self._load_for_update(connection, draft_id)
            connection.commit()
        return self._wire(row)

    def mark_used(self, draft_id: str, used_at: str) -> dict[str, object]:
        draft_id = _required(draft_id, "draftId")
        used_at = _timestamp(used_at, "usedAt")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_for_update(connection, draft_id)
            if row["status"] != "APPROVED":
                raise ValueError("Only an approved AI draft can be marked used")
            connection.execute(
                """
                UPDATE ai_drafts
                SET status = 'USED', used_at = ?, updated_at = ?
                WHERE draft_id = ?
                """,
                (used_at, used_at, draft_id),
            )
            row = self._load_for_update(connection, draft_id)
            connection.commit()
        return self._wire(row)
