import io
import zipfile

import pytest

from munshi_apply_native.resume_parser import parse_resume_bytes, resume_evidence_nodes


def docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        xml = (
            f'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r>'
            "</w:p></w:body></w:document>"
        )
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_docx_resume_becomes_stable_evidence_chunks():
    parsed = parse_resume_bytes(
        "resume.docx",
        docx_bytes(
            "Recruiting experience improved onboarding results with analytics and Excel dashboards."
        ),
    )
    nodes = resume_evidence_nodes(
        resume_id="r1",
        resume_sha256="a" * 64,
        parsed=parsed,
        application_id=None,
        updated_at="2026-08-17T00:00:00+00:00",
    )
    assert parsed.parser == "docx-xml"
    assert nodes
    assert nodes[0]["trust_level"] == "DOCUMENT_CONFIRMED"
    assert "RELEVANT_EXPERIENCE" in nodes[0]["semantic_types"]


def test_legacy_doc_is_explicitly_not_silently_parsed():
    with pytest.raises(ValueError, match="convert it to PDF or DOCX"):
        parse_resume_bytes("resume.doc", b"not-a-modern-doc")
