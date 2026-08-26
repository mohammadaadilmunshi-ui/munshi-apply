from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.document_ingestion import DocumentIngestionService


def make_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                f'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r>'
                "</w:p></w:body></w:document>"
            ),
        )
    return buffer.getvalue()


def test_chunked_resume_ingestion_verifies_hash_and_builds_evidence(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "runtime.sqlite", migrations)
    database.migrate()
    service = DocumentIngestionService(database)
    data = make_docx(
        "Recruiting operations experience improved onboarding and candidate coordination "
        "with Excel analytics."
    )
    digest = hashlib.sha256(data).hexdigest()
    started = service.begin(
        {
            "sessionId": "resume-session-0001",
            "resumeId": "resume-1",
            "filename": "resume.docx",
            "sha256": digest,
            "sizeBytes": len(data),
            "applicationId": None,
        }
    )
    assert started["receivedBytes"] == 0
    service.append(
        {
            "sessionId": "resume-session-0001",
            "offset": 0,
            "base64": base64.b64encode(data).decode("ascii"),
        }
    )
    finished = service.finish({"sessionId": "resume-session-0001"})
    assert finished["sha256"] == digest
    assert finished["evidenceCount"] >= 1
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT kind, trust_level, source FROM evidence_nodes "
            "WHERE source LIKE 'resume:resume-1:%'"
        ).fetchall()
    assert rows
    assert rows[0]["kind"] == "RESUME_BULLET"
    assert rows[0]["trust_level"] == "DOCUMENT_CONFIRMED"
