from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .database import Database
from .models import EventEnvelope
from .n8n import forward_event

BACKOFF_SECONDS = (10, 30, 120, 600, 1800)


@dataclass(frozen=True)
class DeliverySummary:
    claimed: int = 0
    delivered: int = 0
    retry: int = 0
    dead_letter: int = 0


class OutboxWorker:
    def __init__(
        self,
        database: Database,
        webhook_url: str,
        webhook_secret: str,
        *,
        sender: Callable[[str, dict[str, Any], str, float], None] = forward_event,
        max_attempts: int = len(BACKOFF_SECONDS) + 1,
    ) -> None:
        self.database = database
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.sender = sender
        self.max_attempts = max_attempts

    def deliver_due(self, *, now: datetime | None = None, limit: int = 20) -> DeliverySummary:
        clock = now or datetime.now(UTC)
        self.database.recover_stale_outbox(stale_before=(clock - timedelta(minutes=5)).isoformat())
        claimed = self.database.claim_outbox(now=clock.isoformat(), limit=limit)
        delivered = retry = dead_letter = 0
        for row in claimed:
            try:
                event = EventEnvelope.model_validate(
                    json.loads(row["payload_json"])
                ).database_record()
                self.sender(self.webhook_url, event, self.webhook_secret, 5.0)
                self.database.mark_outbox_delivered(row["event_id"], delivered_at=clock.isoformat())
                delivered += 1
            except Exception as error:
                attempt = int(row["attempt_count"])
                delay_index = min(max(attempt - 1, 0), len(BACKOFF_SECONDS) - 1)
                next_retry = clock + timedelta(seconds=BACKOFF_SECONDS[delay_index])
                status = self.database.mark_outbox_failed(
                    row["event_id"],
                    failed_at=clock.isoformat(),
                    next_retry_at=next_retry.isoformat(),
                    error=str(error),
                    max_attempts=self.max_attempts,
                )
                if status == "DEAD_LETTER":
                    dead_letter += 1
                else:
                    retry += 1
        return DeliverySummary(
            claimed=len(claimed), delivered=delivered, retry=retry, dead_letter=dead_letter
        )


async def run_outbox_worker(
    worker: OutboxWorker,
    stop_event: asyncio.Event,
    *,
    poll_seconds: float,
) -> None:
    while not stop_event.is_set():
        await asyncio.to_thread(worker.deliver_due)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            continue
