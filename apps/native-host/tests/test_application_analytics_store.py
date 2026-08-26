from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.application_analytics_store import ApplicationAnalyticsStore
from munshi_apply_native.database import Database

NOW = "2026-08-17T22:30:00+00:00"
LATER = "2026-08-17T22:45:00+00:00"


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "application-analytics.sqlite", migrations)
    result.migrate()
    return result


def test_event_creates_application_and_is_idempotent(tmp_path: Path) -> None:
    db = database(tmp_path)
    store = ApplicationAnalyticsStore(db)
    payload = {
        "eventId": "analytics-event-1",
        "applicationId": "application-1",
        "eventType": "AUTOPILOT_STARTED",
        "occurredAt": NOW,
        "source": "extension",
        "metadata": {"sessionId": "session-1"},
    }

    assert store.record_event(payload) is True
    assert store.record_event(payload) is False

    with db.connect() as connection:
        application = connection.execute(
            "SELECT application_id FROM applications WHERE application_id = ?",
            ("application-1",),
        ).fetchone()
        assert application["application_id"] == "application-1"
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM application_events WHERE event_id = ?",
            ("analytics-event-1",),
        ).fetchone()["count"]
        assert count == 1


def test_job_signal_analytics_remain_descriptive_context(tmp_path: Path) -> None:
    store = ApplicationAnalyticsStore(database(tmp_path))
    payload = {
        "eventId": "job-signals-1",
        "applicationId": "application-1",
        "eventType": "JOB_SIGNALS_ANALYZED",
        "occurredAt": NOW,
        "source": "extension",
        "metadata": {
            "reportId": "report-1",
            "overallScore": 42,
            "statisticalNote": "Observed association only; this does not establish causation.",
        },
    }
    assert store.record_event(payload) is True
    event = store.snapshot()["lifecycleEvents"][0]
    assert event["eventType"] == "JOB_SIGNALS_ANALYZED"
    assert "does not establish causation" in event["metadata"]["statisticalNote"]


def test_same_event_id_cannot_be_rebound(tmp_path: Path) -> None:
    store = ApplicationAnalyticsStore(database(tmp_path))
    original = {
        "eventId": "analytics-event-immutable",
        "applicationId": "application-1",
        "eventType": "PREPARED",
        "occurredAt": NOW,
        "source": "extension",
    }
    assert store.record_event(original) is True
    with pytest.raises(ValueError, match="different immutable event"):
        store.record_event({**original, "eventType": "AUTOPILOT_COMPLETED"})


def test_latest_attribution_context_wins_without_storing_extra_payload(tmp_path: Path) -> None:
    store = ApplicationAnalyticsStore(database(tmp_path))
    assert (
        store.record_context(
            {
                "eventId": "context-old",
                "applicationId": "application-1",
                "capturedAt": NOW,
                "jobSource": "Unknown",
                "atsFamily": "GENERIC",
                "resumeId": "resume-old",
            }
        )
        is True
    )
    assert (
        store.record_context(
            {
                "eventId": "context-new",
                "applicationId": "application-1",
                "capturedAt": LATER,
                "jobSource": "Handshake",
                "atsFamily": "WORKDAY",
                "resumeId": "resume-new",
            }
        )
        is True
    )

    snapshot = store.snapshot()
    assert snapshot["contexts"] == [
        {
            "applicationId": "application-1",
            "capturedAt": LATER,
            "jobSource": "Handshake",
            "atsFamily": "WORKDAY",
            "resumeId": "resume-new",
        }
    ]


def test_outcome_creates_application_and_round_trips(tmp_path: Path) -> None:
    store = ApplicationAnalyticsStore(database(tmp_path))
    payload = {
        "eventId": "outcome-1",
        "applicationId": "application-outcome",
        "stage": "INTERVIEW",
        "occurredAt": NOW,
        "source": "owner",
    }
    assert store.record_outcome(payload) is True
    assert store.record_outcome(payload) is False
    snapshot = store.snapshot()
    assert snapshot["outcomes"] == [payload]


def test_invalid_event_stage_timestamp_and_metadata_fail_closed(tmp_path: Path) -> None:
    store = ApplicationAnalyticsStore(database(tmp_path))
    with pytest.raises(ValueError, match="Unsupported application analytics eventType"):
        store.record_event(
            {
                "eventId": "bad-type",
                "applicationId": "application-1",
                "eventType": "SUBMITTED_SILENTLY",
                "occurredAt": NOW,
                "source": "extension",
            }
        )
    with pytest.raises(ValueError, match="must include a timezone"):
        store.record_outcome(
            {
                "eventId": "bad-time",
                "applicationId": "application-1",
                "stage": "APPLIED",
                "occurredAt": "2026-08-17T22:30:00",
                "source": "owner",
            }
        )
    with pytest.raises(ValueError, match="Unsupported application outcome stage"):
        store.record_outcome(
            {
                "eventId": "bad-stage",
                "applicationId": "application-1",
                "stage": "GHOSTED",
                "occurredAt": NOW,
                "source": "owner",
            }
        )
    with pytest.raises(ValueError, match="metadata must be an object"):
        store.record_event(
            {
                "eventId": "bad-metadata",
                "applicationId": "application-1",
                "eventType": "DETECTED",
                "occurredAt": NOW,
                "source": "extension",
                "metadata": "password=secret",
            }
        )
