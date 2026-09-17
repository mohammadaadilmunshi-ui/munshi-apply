from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.database import Database
from munshi_apply_native.native_messaging import handle

NOW = "2026-08-17T22:30:00+00:00"


def database(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    result = Database(tmp_path / "native-application-analytics.sqlite", migrations)
    result.migrate()
    return result


def test_native_application_analytics_round_trip(tmp_path: Path) -> None:
    db = database(tmp_path)
    context = handle(
        {
            "type": "RECORD_APPLICATION_ATTRIBUTION_CONTEXT",
            "payload": {
                "eventId": "context-1",
                "applicationId": "application-1",
                "capturedAt": NOW,
                "jobSource": "Handshake",
                "atsFamily": "WORKDAY",
                "resumeId": "resume-1",
            },
        },
        db,
    )
    event = handle(
        {
            "type": "RECORD_APPLICATION_ANALYTICS_EVENT",
            "payload": {
                "eventId": "event-1",
                "applicationId": "application-1",
                "eventType": "AUTOPILOT_STARTED",
                "occurredAt": NOW,
                "source": "extension",
                "metadata": {"sessionId": "session-1"},
            },
        },
        db,
    )
    outcome = handle(
        {
            "type": "RECORD_APPLICATION_OUTCOME",
            "payload": {
                "eventId": "outcome-1",
                "applicationId": "application-1",
                "stage": "APPLIED",
                "occurredAt": NOW,
                "source": "owner",
            },
        },
        db,
    )
    snapshot = handle({"type": "GET_APPLICATION_ANALYTICS_SNAPSHOT"}, db)

    assert context == {"ok": True, "data": {"created": True}}
    assert event == {"ok": True, "data": {"created": True}}
    assert outcome == {"ok": True, "data": {"created": True}}
    assert snapshot["ok"] is True
    assert snapshot["data"]["contexts"][0]["jobSource"] == "Handshake"
    assert snapshot["data"]["lifecycleEvents"][0]["eventType"] == "AUTOPILOT_STARTED"
    assert snapshot["data"]["outcomes"][0]["stage"] == "APPLIED"


def test_native_application_analytics_messages_are_idempotent(tmp_path: Path) -> None:
    db = database(tmp_path)
    message = {
        "type": "RECORD_APPLICATION_ANALYTICS_EVENT",
        "payload": {
            "eventId": "event-idempotent",
            "applicationId": "application-1",
            "eventType": "DETECTED",
            "occurredAt": NOW,
            "source": "extension",
        },
    }
    assert handle(message, db)["data"]["created"] is True
    assert handle(message, db)["data"]["created"] is False


def test_native_application_analytics_rejects_timezone_less_events(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must include a timezone"):
        handle(
            {
                "type": "RECORD_APPLICATION_ANALYTICS_EVENT",
                "payload": {
                    "eventId": "event-bad-time",
                    "applicationId": "application-1",
                    "eventType": "DETECTED",
                    "occurredAt": "2026-08-17T22:30:00",
                    "source": "extension",
                },
            },
            database(tmp_path),
        )


def test_native_health_advertises_application_analytics(tmp_path: Path) -> None:
    response = handle({"type": "PING"}, database(tmp_path))
    assert response["ok"] is True
    assert response["data"]["capabilities"]["application_analytics"] is True
