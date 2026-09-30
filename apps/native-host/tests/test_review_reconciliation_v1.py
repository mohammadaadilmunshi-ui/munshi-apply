from __future__ import annotations

from munshi_apply_native.review_reconciliation_v1 import reconcile_provider_review

APPROVED_RESUME = "a" * 64


def _field(
    semantic: str,
    value: str,
    *,
    digest: str = "b" * 64,
    repeat_group: str | None = None,
    repeat_index: int | None = None,
):
    observation = {}
    if repeat_group is not None:
        observation["repeat_group"] = repeat_group
    if repeat_index is not None:
        observation["repeat_index"] = repeat_index
    return {
        "semantic_type": semantic,
        "display_value": value,
        "value_digest": digest,
        "sensitivity_class": "NORMAL",
        "question_observation": observation,
    }


def _prepared_fields():
    return [
        _field("FIRST_NAME", "Ada"),
        _field("MIDDLE_NAME", "Mary"),
        _field("LAST_NAME", "Lovelace"),
        _field("STREET_ADDRESS", "12 Example Street"),
        _field("CITY", "Exampletown"),
        _field("POSTAL_CODE", "12345"),
        _field("PHONE", "(212) 555-0199"),
        _field("PHONE_EXTENSION", ""),
        _field(
            "JOB_TITLE",
            "People Analytics Intern",
            repeat_group="employment",
            repeat_index=0,
        ),
        _field(
            "JOB_TITLE",
            "HR Operations Intern",
            repeat_group="employment",
            repeat_index=1,
        ),
        _field(
            "SCHOOL_NAME",
            "Example University",
            repeat_group="education",
            repeat_index=0,
        ),
    ]


def test_correct_review_matches_without_learning_provider_text():
    review = """
    Review
    Legal Name
    Ms. Ada Mary Lovelace
    Address
    12 Example Street
    Exampletown, NY 12345
    Phone
    +1 (212) 555-0199 (Mobile)
    Work Experience 1
    People Analytics Intern
    Work Experience 2
    HR Operations Intern
    Education 1
    Example University
    Submit
    """
    result = reconcile_provider_review(
        review_text=review,
        prepared_fields=_prepared_fields(),
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256=APPROVED_RESUME,
        final_submission_boundary=True,
    )
    assert result["status"] == "MATCH"
    assert result["mismatches"] == []
    assert len(result["snapshot_digest"]) == 64


def test_review_blocks_phantom_phone_extension():
    review = """
    Review
    Legal Name
    Ms. Ada Mary Lovelace
    Address
    12 Example Street
    Exampletown, NY 12345
    Phone
    +1 (212) 555-0199 x2125550199 (Mobile)
    Work Experience 1
    People Analytics Intern
    Work Experience 2
    HR Operations Intern
    Education 1
    Example University
    Submit
    """
    result = reconcile_provider_review(
        review_text=review,
        prepared_fields=_prepared_fields(),
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256=APPROVED_RESUME,
        final_submission_boundary=True,
    )
    assert result["status"] == "MISMATCH"
    assert "PHONE_EXTENSION_WITHOUT_FACT" in {
        item["code"] for item in result["mismatches"]
    }


def test_review_blocks_overlapping_structured_name_parts():
    fields = _prepared_fields()
    fields[0] = _field("FIRST_NAME", "Ada Mary")
    fields[1] = _field("MIDDLE_NAME", "Mary")
    review = """
    Review
    Legal Name
    Ms. Ada Mary Mary Lovelace
    Address
    12 Example Street
    Exampletown, NY 12345
    Phone
    +1 (212) 555-0199 (Mobile)
    Work Experience 1
    People Analytics Intern
    Work Experience 2
    HR Operations Intern
    Education 1
    Example University
    Submit
    """
    result = reconcile_provider_review(
        review_text=review,
        prepared_fields=fields,
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256=APPROVED_RESUME,
        final_submission_boundary=True,
    )
    assert result["status"] == "MISMATCH"
    assert "NAME_RECOMPOSITION" in {item["code"] for item in result["mismatches"]}


def test_review_blocks_missing_repeated_row():
    review = """
    Review
    Legal Name
    Ms. Ada Mary Lovelace
    Address
    12 Example Street
    Exampletown, NY 12345
    Phone
    +1 (212) 555-0199 (Mobile)
    Work Experience 1
    People Analytics Intern
    Education 1
    Example University
    Submit
    """
    result = reconcile_provider_review(
        review_text=review,
        prepared_fields=_prepared_fields(),
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256=APPROVED_RESUME,
        final_submission_boundary=True,
    )
    assert result["status"] == "MISMATCH"
    assert "REPEAT_GROUP_MISMATCH" in {
        item["code"] for item in result["mismatches"]
    }


def test_review_without_final_boundary_is_incomplete():
    result = reconcile_provider_review(
        review_text="Review",
        prepared_fields=_prepared_fields(),
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256=APPROVED_RESUME,
        final_submission_boundary=False,
    )
    assert result["status"] == "INCOMPLETE"
    assert result["mismatches"][0]["code"] == "MISSING_REQUIRED"


def test_review_blocks_wrong_phone_digits():
    review = """
    Review
    Legal Name
    Ms. Ada Mary Lovelace
    Address
    12 Example Street
    Exampletown, NY 12345
    Phone
    +1 (212) 555-9999 (Mobile)
    Work Experience 1
    People Analytics Intern
    Work Experience 2
    HR Operations Intern
    Education 1
    Example University
    Submit
    """
    result = reconcile_provider_review(
        review_text=review,
        prepared_fields=_prepared_fields(),
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256=APPROVED_RESUME,
        final_submission_boundary=True,
    )
    assert result["status"] == "MISMATCH"
    assert "PHONE_MISMATCH" in {item["code"] for item in result["mismatches"]}


def test_review_blocks_address_drift():
    review = """
    Review
    Legal Name
    Ms. Ada Mary Lovelace
    Address
    99 Different Avenue
    Othercity, NY 99999
    Phone
    +1 (212) 555-0199 (Mobile)
    Work Experience 1
    People Analytics Intern
    Work Experience 2
    HR Operations Intern
    Education 1
    Example University
    Submit
    """
    result = reconcile_provider_review(
        review_text=review,
        prepared_fields=_prepared_fields(),
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256=APPROVED_RESUME,
        final_submission_boundary=True,
    )
    assert result["status"] == "MISMATCH"
    assert "ADDRESS_MISMATCH" in {item["code"] for item in result["mismatches"]}


def test_review_blocks_wrong_resume_artifact_sha():
    review = """
    Review
    Legal Name
    Ms. Ada Mary Lovelace
    Address
    12 Example Street
    Exampletown, NY 12345
    Phone
    +1 (212) 555-0199 (Mobile)
    Work Experience 1
    People Analytics Intern
    Work Experience 2
    HR Operations Intern
    Education 1
    Example University
    Submit
    """
    result = reconcile_provider_review(
        review_text=review,
        prepared_fields=_prepared_fields(),
        expected_resume_sha256=APPROVED_RESUME,
        observed_resume_sha256="c" * 64,
        final_submission_boundary=True,
    )
    assert result["status"] == "MISMATCH"
    assert "RESUME_SHA_MISMATCH" in {
        item["code"] for item in result["mismatches"]
    }
