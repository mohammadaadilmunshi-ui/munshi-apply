from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def update(path: str, replacements: list[tuple[str, str]]) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    for old, new in replacements:
        if old not in content:
            raise RuntimeError(f"{path}: expected quality replacement not found: {old[:90]!r}")
        content = content.replace(old, new, 1)
    target.write_text(content, encoding="utf-8")


update(
    "apps/native-host/src/munshi_apply_native/providers.py",
    [
        (
            '        "and verified results. For career-transition answers, stay constructive and future-focused. "\n',
            '        "and verified results. For career-transition answers, stay constructive and "\n'
            '        "future-focused. "\n',
        )
    ],
)

update(
    "apps/native-host/src/munshi_apply_native/response_planner.py",
    [
        (
            '        r"why (?:do you want to (?:work|join)|are you interested in) (?:us|our|this company|the company)",\n',
            '        r"why (?:do you want to (?:work|join)|are you interested in) "\n'
            '        r"(?:us|our|this company|the company)",\n',
        ),
        (
            '        r"why (?:this|the) (?:role|position)|why are you interested in (?:this|the) (?:role|position)",\n',
            '        r"why (?:this|the) (?:role|position)|why are you interested in "\n'
            '        r"(?:this|the) (?:role|position)",\n',
        ),
        (
            '        r"what (?:does|do you understand about).*(?:role|position)|describe (?:the )?(?:role|responsibilities)",\n',
            '        r"what (?:does|do you understand about).*(?:role|position)|describe "\n'
            '        r"(?:the )?(?:role|responsibilities)",\n',
        ),
        (
            '        r"(?:relevant|related|prior) experience|tell us about your experience|describe your experience",\n',
            '        r"(?:relevant|related|prior) experience|tell us about your experience|"\n'
            '        r"describe your experience",\n',
        ),
    ],
)

update(
    "apps/native-host/tests/test_document_ingestion.py",
    [
        (
            '            f\'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>\',\n',
            '            (\n'
            '                f\'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r>\'\n'
            '                "</w:p></w:body></w:document>"\n'
            '            ),\n',
        ),
        (
            '        "Recruiting operations experience improved onboarding and candidate coordination with Excel analytics."\n',
            '        "Recruiting operations experience improved onboarding and candidate coordination "\n'
            '        "with Excel analytics."\n',
        ),
        (
            '            "SELECT kind, trust_level, source FROM evidence_nodes WHERE source LIKE \'resume:resume-1:%\'"\n',
            '            "SELECT kind, trust_level, source FROM evidence_nodes "\n'
            '            "WHERE source LIKE \'resume:resume-1:%\'"\n',
        ),
    ],
)

update(
    "apps/native-host/tests/test_resume_parser.py",
    [
        (
            '        archive.writestr("word/document.xml", f\'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>\')\n',
            '        xml = (\n'
            '            f\'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r>\'\n'
            '            "</w:p></w:body></w:document>"\n'
            '        )\n'
            '        archive.writestr("word/document.xml", xml)\n',
        )
    ],
)

update(
    "apps/native-host/tests/test_writing_style.py",
    [
        (
            '        "I’m interested because the role connects recruiting operations with analytics, which matches my experience.",\n',
            '        "I’m interested because the role connects recruiting operations with analytics, "\n'
            '        "which matches my experience.",\n',
        )
    ],
)
