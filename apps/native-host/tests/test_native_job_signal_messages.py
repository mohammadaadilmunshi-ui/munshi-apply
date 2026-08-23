from __future__ import annotations

from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle

NOW = "2026-08-17T20:25:00+00:00"
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
    result = Database(tmp_path / "native-job-signals.sqlite", migrations)
    result.migrate()
    return result


def report_payload() -> dict[str, object]:
    return {
        "reportId": "report-native",
        "applicationId": "application-native",
        "jobId": "job-application-native",
        "sourceIdentity": "https://jobs.example.com/application-native",
        "overallSignal": "MODERATE",
        "overallScore": 44,
        "sourceFingerprint": "source-native-1",
        "evaluatedAt": NOW,
        "dimensions": {
            dimension: {
                "dimension": dimension,
                "score": 58 if dimension == "WORKLOAD_PRESSURE" else None,
                "confidence": 0.9 if dimension == "WORKLOAD_PRESSURE" else 0.0,
                "evidenceIds": (["signal-native"] if dimension == "WORKLOAD_PRESSURE" else []),
            }
            for dimension in DIMENSIONS
        },
        "signals": [
            {
                "signalId": "signal-native",
                "dimension": "WORKLOAD_PRESSURE",
                "severity": "MODERATE",
                "direction": "NEUTRAL",
                "source": "JOB_POSTING",
                "evidence": "high-volume environment",
                "explanation": "The posting explicitly describes high-volume work.",
            }
        ],
    }


def test_native_job_signal_save_ensures_application_and_round_trips(tmp_path: Path) -> None:
    db = database(tmp_path)
    saved = handle(
        {"type": "SAVE_JOB_SIGNAL_REPORT", "payload": report_payload()},
        db,
    )

    assert saved["ok"] is True
    assert saved["data"]["reportId"] == "report-native"
    assert saved["data"]["overallScore"] == 44

    latest = handle(
        {
            "type": "GET_LATEST_JOB_SIGNAL_REPORT",
            "payload": {
                "applicationId": "application-native",
                "jobId": "job-application-native",
                "sourceIdentity": "https://jobs.example.com/application-native",
            },
        },
        db,
    )
    assert latest == saved

    with db.connect() as connection:
        application = connection.execute(
            """
            SELECT application_id, job_signal_score
            FROM applications
            WHERE application_id = ?
            """,
            ("application-native",),
        ).fetchone()
        assert application["application_id"] == "application-native"
        assert application["job_signal_score"] == 44


def test_native_job_signal_lookup_returns_none_before_report_exists(tmp_path: Path) -> None:
    response = handle(
        {
            "type": "GET_LATEST_JOB_SIGNAL_REPORT",
            "payload": {
                "applicationId": "application-missing-report",
                "jobId": "job-application-missing-report",
            },
        },
        database(tmp_path),
    )
    assert response == {"ok": True, "data": None}


def test_native_job_signal_save_rejects_timezone_less_evaluation(tmp_path: Path) -> None:
    payload = report_payload()
    payload["evaluatedAt"] = "2026-08-17T20:25:00"

    try:
        handle({"type": "SAVE_JOB_SIGNAL_REPORT", "payload": payload}, database(tmp_path))
    except ValueError as error:
        assert "must include a timezone" in str(error)
    else:
        raise AssertionError("Timezone-less Job Signal report was accepted")


def test_native_health_advertises_job_signal_intelligence(tmp_path: Path) -> None:
    response = handle({"type": "PING"}, database(tmp_path))
    assert response["ok"] is True
    assert response["data"]["capabilities"]["job_signal_intelligence"] is True
    assert response["data"]["capabilities"]["job_signal_identity_binding"] is True
