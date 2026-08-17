from __future__ import annotations

import io
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle, read_message, write_message


def test_native_message_round_trip() -> None:
    stream = io.BytesIO()
    write_message(stream, {"type": "PING"})
    stream.seek(0)
    assert read_message(stream) == {"type": "PING"}


def test_ping_advertises_current_protocol_and_capabilities(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    database = Database(tmp_path / "native.sqlite", repository_root / "migrations")
    database.migrate()

    response = handle({"type": "PING"}, database)

    assert response["ok"] is True
    data = response["data"]
    assert isinstance(data, dict)
    assert data["protocol_version"] == 3
    assert data["capabilities"]["ai_governance"] is True
    assert data["capabilities"]["ai_draft_lifecycle"] is True
    assert data["capabilities"]["profile_vault"] is True
    assert data["capabilities"]["document_evidence_ingestion"] is True
    assert data["capabilities"]["provider_routing"] is True
    assert data["capabilities"]["writing_style_learning"] is True
    assert data["capabilities"]["teach_munshi_state_capture"] is True
