from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.outbox import OutboxWorker


def event_record(event_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "correlation_id": "correlation-outbox",
        "application_id": None,
        "event_type": "PAGE_DETECTED",
        "occurred_at": "2026-08-14T12:00:00+00:00",
        "source": "munshi-apply",
        "payload": {"controls": 4},
    }


def database_at(tmp_path: Path) -> Database:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "outbox.sqlite", migrations)
    database.migrate()
    return database


def test_outbox_delivery_marks_event_delivered(tmp_path: Path) -> None:
    database = database_at(tmp_path)
    database.record_event(event_record("evt-deliver"))
    sent: list[dict[str, object]] = []

    def sender(_: str, event: dict[str, object], __: str, ___: float) -> None:
        sent.append(event)

    worker = OutboxWorker(database, "https://example.test/hook", "secret", sender=sender)
    summary = worker.deliver_due(now=datetime(2026, 8, 14, 12, 0, tzinfo=UTC))

    assert summary.delivered == 1
    assert sent[0]["event_id"] == "evt-deliver"
    assert database.outbox_counts()["DELIVERED"] == 1


def test_failed_delivery_retries_without_losing_ledger_event(tmp_path: Path) -> None:
    database = database_at(tmp_path)
    database.record_event(event_record("evt-retry"))

    def sender(_: str, __: dict[str, object], ___: str, ____: float) -> None:
        raise ConnectionError("n8n unavailable")

    worker = OutboxWorker(database, "https://example.test/hook", "secret", sender=sender)
    summary = worker.deliver_due(now=datetime(2026, 8, 14, 12, 0, tzinfo=UTC))

    assert summary.retry == 1
    assert database.outbox_counts()["RETRY"] == 1
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0] == 1


def test_retry_limit_moves_event_to_dead_letter(tmp_path: Path) -> None:
    database = database_at(tmp_path)
    database.record_event(event_record("evt-dead-letter"))

    def sender(_: str, __: dict[str, object], ___: str, ____: float) -> None:
        raise TimeoutError("n8n timeout")

    worker = OutboxWorker(
        database,
        "https://example.test/hook",
        "secret",
        sender=sender,
        max_attempts=1,
    )
    summary = worker.deliver_due(now=datetime(2026, 8, 14, 12, 0, tzinfo=UTC))

    assert summary.dead_letter == 1
    assert database.outbox_counts()["DEAD_LETTER"] == 1


def test_stale_in_flight_delivery_is_recovered(tmp_path: Path) -> None:
    database = database_at(tmp_path)
    database.record_event(event_record("evt-stale"))
    database.claim_outbox(now="2026-08-14T11:00:00+00:00")
    sent: list[str] = []

    def sender(_: str, event: dict[str, object], __: str, ___: float) -> None:
        sent.append(str(event["event_id"]))

    worker = OutboxWorker(database, "https://example.test/hook", "secret", sender=sender)
    summary = worker.deliver_due(now=datetime(2026, 8, 14, 12, 0, tzinfo=UTC))

    assert summary.delivered == 1
    assert sent == ["evt-stale"]


def test_malformed_outbox_event_is_not_delivered(tmp_path: Path) -> None:
    database = database_at(tmp_path)
    database.record_event(event_record("evt-malformed"))
    with database.connect() as connection:
        connection.execute(
            "UPDATE outbox_events SET payload_json = '{}' WHERE event_id = 'evt-malformed'"
        )
    sent: list[str] = []

    def sender(_: str, __: dict[str, object], ___: str, ____: float) -> None:
        sent.append("sent")

    worker = OutboxWorker(
        database,
        "https://example.test/hook",
        "secret",
        sender=sender,
        max_attempts=1,
    )
    summary = worker.deliver_due(now=datetime(2026, 8, 14, 12, 0, tzinfo=UTC))

    assert summary.dead_letter == 1
    assert sent == []
