from __future__ import annotations

from pathlib import Path

from munshi_apply_native.application_store import ApplicationStore
from munshi_apply_native.database import Database
from munshi_apply_native.job_signal_store import JobSignalStore

NOW = "2026-08-17T20:15:00+00:00"
DIMENSIONS = (
    "ROLE_AMBIGUITY",
    "RESPONSIBILITY_BREADTH",
    "QUALIFICATION_INFLATION",
    "WORKLOAD_PRESSURE",
    "SCHEDULE_INTENSITY",
    "TRAVEL_BURDEN",
    "COMPENSATION_CLARITY",
    "SENIORITY_ALIGNMENT",
    "ROLE_STABILITY",
    "LOCATION_CONSTRAINTS",
    "WORK_AUTHORIZATION_RISK",
    "APPLICATION_FRICTION",
)


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "job-signals.sqlite", migrations)
    result.migrate()
    return result


def report_payload(
    *,
    report_id: str = "report-1",
    score: int = 41,
    evidence: str = "Up to 40% travel",
) -> dict[str, object]:
    dimensions = {
        dimension: {
            "dimension": dimension,
            "score": 70 if dimension == "TRAVEL_BURDEN" else None,
            "confidence": 0.98 if dimension == "TRAVEL_BURDEN" else 0.0,
            "evidenceIds": ["signal-travel"] if dimension == "TRAVEL_BURDEN" else [],
        }
        for dimension in DIMENSIONS
    }
    return {
        "reportId": report_id,
        "applicationId": "application-1",
        "overallSignal": "MODERATE",
        "overallScore": score,
        "sourceFingerprint": "source-fingerprint-1",
        "evaluatedAt": NOW,
        "dimensions": dimensions,
        "signals": [
            {
                "signalId": "signal-travel",
                "dimension": "TRAVEL_BURDEN",
                "severity": "HIGH",
                "evidence": evidence,
                "explanation": "The posting explicitly states a 40% travel expectation.",
            }
        ],
    }


def test_job_signal_report_round_trip_updates_application_summary(tmp_path: Path) -> None:
    db = database(tmp_path)
    ApplicationStore(db).ensure("application-1", NOW)
    store = JobSignalStore(db)

    saved = store.save(report_payload())

    assert saved["reportId"] == "report-1"
    assert saved["overallScore"] == 41
    assert saved["dimensions"]["TRAVEL_BURDEN"]["score"] == 70
    assert saved["dimensions"]["TRAVEL_BURDEN"]["evidenceIds"] == ["signal-travel"]
    assert saved["signals"][0]["evidence"] == "Up to 40% travel"
    assert store.latest("application-1") == saved

    with db.connect() as connection:
        summary = connection.execute(
            "SELECT job_signal_score FROM applications WHERE application_id = ?",
            ("application-1",),
        ).fetchone()[0]
        assert summary == 41
        assert connection.execute("SELECT COUNT(*) FROM job_signal_reports").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM job_signal_dimensions").fetchone()[0] == 12
        assert connection.execute("SELECT COUNT(*) FROM job_signal_evidence").fetchone()[0] == 1


def test_same_source_fingerprint_replaces_report_content_without_duplicate_identity(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    ApplicationStore(db).ensure("application-1", NOW)
    store = JobSignalStore(db)

    first = store.save(report_payload())
    replacement = report_payload(
        report_id="ignored-new-report-id",
        score=52,
        evidence="Travel may reach 40% depending on business need",
    )
    replacement["evaluatedAt"] = "2026-08-17T20:20:00+00:00"
    second = store.save(replacement)

    assert first["reportId"] == "report-1"
    assert second["reportId"] == "report-1"
    assert second["overallScore"] == 52
    assert second["signals"][0]["evidence"].startswith("Travel may reach")
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job_signal_reports").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM job_signal_dimensions").fetchone()[0] == 12
        assert connection.execute("SELECT COUNT(*) FROM job_signal_evidence").fetchone()[0] == 1


def test_invalid_cross_dimension_evidence_is_rejected_without_partial_write(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    ApplicationStore(db).ensure("application-1", NOW)
    payload = report_payload()
    payload["dimensions"]["TRAVEL_BURDEN"]["evidenceIds"] = []
    payload["dimensions"]["WORKLOAD_PRESSURE"]["evidenceIds"] = ["signal-travel"]

    try:
        JobSignalStore(db).save(payload)
    except ValueError as error:
        assert "same dimension" in str(error)
    else:
        raise AssertionError("Cross-dimension Job Signal evidence was accepted")

    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job_signal_reports").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM job_signal_dimensions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM job_signal_evidence").fetchone()[0] == 0
        assert connection.execute(
            "SELECT job_signal_score FROM applications WHERE application_id = ?",
            ("application-1",),
        ).fetchone()[0] is None


def test_report_requires_complete_canonical_dimension_set(tmp_path: Path) -> None:
    db = database(tmp_path)
    ApplicationStore(db).ensure("application-1", NOW)
    payload = report_payload()
    del payload["dimensions"]["ROLE_AMBIGUITY"]

    try:
        JobSignalStore(db).save(payload)
    except ValueError as error:
        assert "complete canonical Job Signal ontology" in str(error)
    else:
        raise AssertionError("Incomplete Job Signal ontology was accepted")
