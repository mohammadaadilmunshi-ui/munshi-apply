from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .architecture_store import ArchitectureStore
from .database import Database
from .resume_parser import parse_resume_bytes, resume_evidence_nodes

_MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
_MAX_CHUNK_BYTES = 512 * 1024
_SESSION_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{8,120}$")


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


class DocumentIngestionService:
    """Durable chunked ingestion for résumé bytes sent through Native Messaging."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.root = database.path.parent / "document-ingestion"
        self.architecture = ArchitectureStore(database)

    def _paths(self, session_id: str) -> tuple[Path, Path]:
        if not _SESSION_PATTERN.fullmatch(session_id):
            raise ValueError("Document ingestion sessionId is invalid")
        return self.root / f"{session_id}.json", self.root / f"{session_id}.part"

    def begin(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Document ingestion payload must be an object")
        session_id = _required(payload, "sessionId")
        resume_id = _required(payload, "resumeId")
        filename = _required(payload, "filename")
        expected_sha256 = _required(payload, "sha256").lower()
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise ValueError("Résumé SHA-256 is invalid")
        size = payload.get("sizeBytes")
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= _MAX_DOCUMENT_BYTES:
            raise ValueError("Résumé size must be between 1 byte and 12 MB")
        application_id = payload.get("applicationId")
        if application_id is not None and (not isinstance(application_id, str) or not application_id.strip()):
            raise ValueError("applicationId must be a non-empty string when provided")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        meta_path, part_path = self._paths(session_id)
        metadata = {
            "sessionId": session_id,
            "resumeId": resume_id,
            "filename": filename,
            "sha256": expected_sha256,
            "sizeBytes": size,
            "applicationId": application_id.strip() if isinstance(application_id, str) else None,
            "receivedBytes": 0,
            "startedAt": datetime.now(UTC).isoformat(),
        }
        meta_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        part_path.write_bytes(b"")
        os.chmod(meta_path, 0o600)
        os.chmod(part_path, 0o600)
        return {"sessionId": session_id, "receivedBytes": 0, "maxChunkBytes": _MAX_CHUNK_BYTES}

    def _load(self, session_id: str) -> tuple[dict[str, Any], Path, Path]:
        meta_path, part_path = self._paths(session_id)
        if not meta_path.exists() or not part_path.exists():
            raise ValueError("Document ingestion session does not exist")
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Document ingestion session metadata is unreadable") from error
        if not isinstance(metadata, dict):
            raise ValueError("Document ingestion session metadata is invalid")
        return metadata, meta_path, part_path

    def append(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Document chunk payload must be an object")
        session_id = _required(payload, "sessionId")
        encoded = _required(payload, "base64")
        offset = payload.get("offset")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Document chunk offset must be a non-negative integer")
        try:
            data = base64.b64decode(encoded, validate=True)
        except Exception as error:
            raise ValueError("Document chunk is not valid base64") from error
        if not data or len(data) > _MAX_CHUNK_BYTES:
            raise ValueError("Document chunk must contain 1-512 KB")
        metadata, meta_path, part_path = self._load(session_id)
        received = int(metadata.get("receivedBytes", -1))
        expected_size = int(metadata.get("sizeBytes", 0))
        if offset != received:
            raise ValueError(f"Document chunk offset mismatch; expected {received}")
        if received + len(data) > expected_size:
            raise ValueError("Document chunk exceeds declared résumé size")
        with part_path.open("ab") as handle:
            handle.write(data)
        received += len(data)
        metadata["receivedBytes"] = received
        meta_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        os.chmod(meta_path, 0o600)
        return {"sessionId": session_id, "receivedBytes": received, "complete": received == expected_size}

    def finish(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Document finish payload must be an object")
        session_id = _required(payload, "sessionId")
        metadata, meta_path, part_path = self._load(session_id)
        expected_size = int(metadata["sizeBytes"])
        if int(metadata.get("receivedBytes", -1)) != expected_size or part_path.stat().st_size != expected_size:
            raise ValueError("Résumé ingestion is incomplete")
        data = part_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != metadata["sha256"]:
            raise ValueError("Résumé bytes do not match the encrypted-vault SHA-256")
        parsed = parse_resume_bytes(str(metadata["filename"]), data)
        now = datetime.now(UTC).isoformat()
        nodes = resume_evidence_nodes(
            resume_id=str(metadata["resumeId"]),
            resume_sha256=digest,
            parsed=parsed,
            application_id=metadata.get("applicationId"),
            updated_at=now,
        )
        source_prefix = f"resume:{metadata['resumeId']}:"
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM evidence_nodes WHERE source LIKE ?", (source_prefix + "%",))
        for node in nodes:
            self.architecture.upsert_evidence_node(node)
        self._cleanup(meta_path, part_path)
        return {
            "sessionId": session_id,
            "resumeId": metadata["resumeId"],
            "sha256": digest,
            "parser": parsed.parser,
            "evidenceCount": len(nodes),
            "characterCount": len(parsed.text),
            "warnings": list(parsed.warnings),
        }

    def cancel(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Document cancel payload must be an object")
        session_id = _required(payload, "sessionId")
        meta_path, part_path = self._paths(session_id)
        existed = meta_path.exists() or part_path.exists()
        self._cleanup(meta_path, part_path)
        return {"sessionId": session_id, "cancelled": existed}

    @staticmethod
    def _cleanup(meta_path: Path, part_path: Path) -> None:
        for path in (part_path, meta_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
