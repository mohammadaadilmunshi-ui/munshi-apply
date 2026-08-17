from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

from defusedxml import ElementTree
from pypdf import PdfReader

_MAX_TEXT_CHARACTERS = 120_000
_CHUNK_TARGET = 900
_CHUNK_HARD_MAX = 1_400


@dataclass(frozen=True)
class ParsedResume:
    text: str
    chunks: tuple[str, ...]
    parser: str
    warnings: tuple[str, ...]


def _normalize(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:_MAX_TEXT_CHARACTERS]


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        try:
            xml = archive.read("word/document.xml")
        except KeyError as error:
            raise ValueError("DOCX does not contain word/document.xml") from error
    root = ElementTree.fromstring(xml)
    pieces: list[str] = []
    for element in root.iter():
        if element.tag.endswith("}t") and element.text:
            pieces.append(element.text)
        elif element.tag.endswith("}p"):
            pieces.append("\n")
    return " ".join(pieces).replace(" \n ", "\n")


def _chunks(text: str) -> tuple[str, ...]:
    paragraphs = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"\n+", text)]
    paragraphs = [item for item in paragraphs if item]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > _CHUNK_HARD_MAX:
            sentences = [
                item.strip() for item in re.split(r"(?<=[.!?])\s+", paragraph) if item.strip()
            ]
        else:
            sentences = [paragraph]
        for sentence in sentences:
            if not current:
                current = sentence
                continue
            candidate = f"{current} {sentence}"
            if len(candidate) <= _CHUNK_TARGET:
                current = candidate
            else:
                chunks.append(current[:_CHUNK_HARD_MAX])
                current = sentence
    if current:
        chunks.append(current[:_CHUNK_HARD_MAX])
    return tuple(chunks[:120])


def parse_resume_bytes(filename: str, data: bytes) -> ParsedResume:
    suffix = PurePath(filename).suffix.lower()
    if not data:
        raise ValueError("Résumé is empty")
    warnings: list[str] = []
    try:
        if suffix == ".pdf":
            raw = _pdf_text(data)
            parser = "pypdf"
        elif suffix == ".docx":
            raw = _docx_text(data)
            parser = "docx-xml"
        elif suffix in {".txt", ".md"}:
            raw = data.decode("utf-8", errors="replace")
            parser = "text"
        elif suffix == ".doc":
            raise ValueError(
                "Legacy .doc parsing is not deterministic in the native companion; "
                "convert it to PDF or DOCX"
            )
        else:
            raise ValueError("Supported evidence parsing formats are PDF, DOCX, TXT, and MD")
    except Exception as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"Résumé parser could not read {suffix or 'this file'}") from error
    text = _normalize(raw)
    if len(text) < 40:
        raise ValueError(
            "Résumé contains too little extractable text; scanned/image-only documents "
            "need a text-readable version"
        )
    if len(raw) > _MAX_TEXT_CHARACTERS:
        warnings.append("Extracted résumé text was truncated to the evidence ingestion limit")
    chunks = _chunks(text)
    if not chunks:
        raise ValueError("Résumé parser produced no evidence chunks")
    return ParsedResume(text=text, chunks=chunks, parser=parser, warnings=tuple(warnings))


def _semantic_types(text: str) -> list[str]:
    lowered = text.lower()
    types: set[str] = set()
    experience_terms = (
        "experience",
        "recruit",
        "human resources",
        "hr ",
        "talent",
        "workforce",
        "people analytics",
        "onboarding",
    )
    if any(term in lowered for term in experience_terms):
        types.update({"RELEVANT_EXPERIENCE", "WHY_ROLE", "MOTIVATION"})
    result_terms = (
        "achieved",
        "improved",
        "reduced",
        "increased",
        "%",
        "result",
        "delivered",
        "managed",
        "led",
    )
    if any(term in lowered for term in result_terms):
        types.add("BEHAVIORAL_EXAMPLE")
    education_terms = ("education", "university", "master", "bachelor", "degree", "gpa")
    if any(term in lowered for term in education_terms):
        types.add("EDUCATION")
    project_terms = (
        "project",
        "dashboard",
        "python",
        "tableau",
        "power bi",
        "excel",
        "analytics",
    )
    if any(term in lowered for term in project_terms):
        types.update({"PROJECT", "RELEVANT_EXPERIENCE"})
    return sorted(types)


def resume_evidence_nodes(
    *,
    resume_id: str,
    resume_sha256: str,
    parsed: ParsedResume,
    application_id: str | None,
    updated_at: str,
) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    for index, text in enumerate(parsed.chunks):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
        nodes.append(
            {
                "evidence_id": f"resume-{resume_sha256[:16]}-{index:03d}-{digest}",
                "application_id": application_id,
                "kind": "RESUME_BULLET",
                "text": text,
                "semantic_types": _semantic_types(text),
                "trust_level": "DOCUMENT_CONFIRMED",
                "protected": False,
                "source": f"resume:{resume_id}:{resume_sha256}",
                "updated_at": updated_at,
            }
        )
    return nodes
