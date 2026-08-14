from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle


def create_database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-1', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (now, now),
        )
    return database


def checkpoint_payload(*, checkpoint_id: str = "cp-1", sequence: int = 1) -> dict[str, object]:
    return {
        "checkpointId": checkpoint_id,
        "applicationId": "app-1",
        "sequence": sequence,
        "state": "PERSONAL",
        "pageId": "page-1",
        "pageFingerprint": f"fingerprint-{sequence}",
        "completedControlIds": ["control-1"],
        "pendingControlIds": ["control-2"],
        "selectedResumeId": None,
        "selectedResumeSha256": None,
        "createdAt": "2026-08-14T21:00:00Z",
    }


def test_checkpoint_save_is_idempotent_and_readable(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    message = {"type": "SAVE_APPLICATION_CHECKPOINT", "payload": checkpoint_payload()}

    first = handle(message, database)
    second = handle(message, database)

    assert first["ok"] is True
    assert first["data"]["created"] is True  # type: ignore[index]
    assert second["data"]["created"] is False  # type: ignore[index]

    latest = handle(
        {
            "type": "GET_LATEST_APPLICATION_CHECKPOINT",
            "payload": {"applicationId": "app-1"},
        },
        database,
    )
    assert latest["ok"] is True
    assert latest["data"]["checkpointId"] == "cp-1"  # type: ignore[index]
    assert latest["data"]["sequence"] == 1  # type: ignore[index]


def test_checkpoint_sequence_reuse_with_different_content_is_rejected(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    first = checkpoint_payload()
    handle({"type": "SAVE_APPLICATION_CHECKPOINT", "payload": first}, database)

    conflicting = {**first, "pageFingerprint": "different"}
    with pytest.raises(ValueError, match="different content"):
        handle(
            {"type": "SAVE_APPLICATION_CHECKPOINT", "payload": conflicting},
            database,
        )


def test_checkpoint_sequence_cannot_move_backward(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    handle(
        {
            "type": "SAVE_APPLICATION_CHECKPOINT",
            "payload": checkpoint_payload(checkpoint_id="cp-2", sequence=2),
        },
        database,
    )
    with pytest.raises(ValueError, match="advance monotonically"):
        handle(
            {
                "type": "SAVE_APPLICATION_CHECKPOINT",
                "payload": checkpoint_payload(checkpoint_id="cp-1", sequence=1),
            },
            database,
        )


def test_checkpoint_payload_rejects_overlap_and_partial_resume_identity(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    overlap = {
        **checkpoint_payload(),
        "pendingControlIds": ["control-1"],
    }
    with pytest.raises(ValueError, match="must not overlap"):
        handle({"type": "SAVE_APPLICATION_CHECKPOINT", "payload": overlap}, database)

    partial_resume = {
        **checkpoint_payload(),
        "selectedResumeId": "resume-1",
        "selectedResumeSha256": None,
    }
    with pytest.raises(ValueError, match="stored together"):
        handle(
            {"type": "SAVE_APPLICATION_CHECKPOINT", "payload": partial_resume},
            database,
        )
