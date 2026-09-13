from __future__ import annotations

import asyncio
from typing import Any

from .database import Database
from .teach_munshi_service import TeachMunshiService


class TeachMunshiLearningWorker:
    """Continuously drains verified Teach MUNSHI lessons off the application path.

    The queue already contains normalized, value-free interaction mechanics. This
    worker performs local SQLite/recipe work only; it never invokes an AI provider
    and therefore cannot add model latency or model cost to an application.
    """

    def __init__(
        self,
        database: Database,
        *,
        batch_size: int = 16,
    ) -> None:
        self.service = TeachMunshiService(database)
        self.batch_size = max(1, min(100, int(batch_size)))

    def drain_once(self) -> int:
        result = self.service.drain(limit=self.batch_size)
        return int(result["learned"]) + int(result["failed"])


async def run_teach_munshi_learning_worker(
    worker: TeachMunshiLearningWorker,
    stop_event: Any,
    *,
    poll_seconds: float = 0.25,
) -> None:
    """Drain learning work in a thread so browser/runtime requests never wait."""

    poll = max(0.05, float(poll_seconds))
    while not stop_event.is_set():
        processed = await asyncio.to_thread(worker.drain_once)
        if processed >= worker.batch_size:
            # A full batch means backlog may remain. Yield once and immediately
            # continue rather than imposing a fixed delay on catch-up work.
            await asyncio.sleep(0)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll)
        except TimeoutError:
            continue
