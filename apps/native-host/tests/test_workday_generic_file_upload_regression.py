from pathlib import Path


def _source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "munshi_apply_native"
        / "plan_browser_adapter.py"
    ).read_text()


def test_single_file_resume_fallback_is_not_disabled_by_bound_cover_letter():
    source = _source()
    assert "and not cover_letter_role" in source
    assert 'and not isinstance(plan.get("cover_letter"), dict)' not in source


def test_explicit_cover_letter_role_is_checked_before_single_file_resume_fallback():
    source = _source()
    cover_pos = source.index("cover_letter_role = (")
    resume_pos = source.index("resume_role = bool(", cover_pos)
    fallback_pos = source.index("and not cover_letter_role", resume_pos)
    upload_pos = source.index('if resume_role:', fallback_pos)
    cover_branch_pos = source.index("cover_letter_role", upload_pos)
    assert cover_pos < resume_pos < fallback_pos < upload_pos < cover_branch_pos
