from __future__ import annotations

import hashlib

from munshi_apply_native.universal_document_uploader import (
    DocumentSpec,
    UniversalDocumentUploader,
    classify_upload_identity,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


check(classify_upload_identity("Upload Resume") == "resume", "resume classification")
check(classify_upload_identity("Curriculum Vitae") == "resume", "CV classification")
check(classify_upload_identity("Upload Cover Letter") == "cover_letter", "cover classification")
check(classify_upload_identity("Drag and drop document") == "generic", "generic classification")
check(classify_upload_identity("Something unrelated") == "unknown", "unknown classification")

data = b"exact immutable artifact"
spec = DocumentSpec(
    role="resume",
    filename="resume.pdf",
    mime_type="application/pdf",
    sha256=hashlib.sha256(data).hexdigest(),
    data=data,
)
check(spec.validated() is spec, "digest validation")

one_generic = [{"role": "generic", "meta": {}}]
check(
    UniversalDocumentUploader._candidate_for_role(
        one_generic, role="resume", allow_generic_single=True
    )
    is one_generic[0],
    "single generic resume fallback",
)

two_generic = [
    {"role": "generic", "meta": {}},
    {"role": "generic", "meta": {}},
]
check(
    UniversalDocumentUploader._candidate_for_role(
        two_generic, role="resume", allow_generic_single=True
    )
    is None,
    "multiple ambiguous targets must fail closed",
)

mixed = [
    {"role": "cover_letter", "meta": {}},
    {"role": "generic", "meta": {}},
]
check(
    UniversalDocumentUploader._candidate_for_role(
        mixed, role="resume", allow_generic_single=True
    )
    is mixed[1],
    "resume can use sole non-cover generic target",
)
check(
    UniversalDocumentUploader._candidate_for_role(
        mixed, role="cover_letter", allow_generic_single=False
    )
    is mixed[0],
    "explicit cover-letter target",
)

print("UNIVERSAL_DOCUMENT_UPLOADER_SELFTEST=PASS")
