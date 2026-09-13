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
        stale_after_seconds: int = 120,
    ) -> None:
        self.service = TeachMunshiService(database)
        self.batch_size = max(1, int(batch_size))
        self.stale_after_seconds = max(30, int(stale_after_seconds))

    def drain_once(self) -> int:
        self.service.recover_stale(stale_after_seconds=self.stale_after_seconds)
        processed = 0
        for _ in range(self.batch_size):
            result = self.service.process_next()
            if result is None:
                break
            processed += 1
        return processed


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
            # Backlog exists; immediately yield and continue draining without a
            # fixed sleep while still allowing cancellation/other tasks to run.
            await asyncio.sleep(0)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll)
        except TimeoutError:
            continue
