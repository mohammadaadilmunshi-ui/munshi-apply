from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from . import __version__
from .database import Database
from .models import EventEnvelope, HealthResponse
from .outbox import OutboxWorker, run_outbox_worker
from .settings import Settings

settings = Settings.from_environment()
database = Database(settings.database_path, settings.migrations_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.migrate()
    stop_event = None
    worker_task = None
    if settings.n8n_webhook_url and settings.n8n_webhook_secret:
        import asyncio

        stop_event = asyncio.Event()
        worker = OutboxWorker(database, settings.n8n_webhook_url, settings.n8n_webhook_secret)
        worker_task = asyncio.create_task(
            run_outbox_worker(worker, stop_event, poll_seconds=settings.outbox_poll_seconds)
        )
    yield
    if stop_event and worker_task:
        stop_event.set()
        await worker_task


app = FastAPI(
    title="MUNSHI Apply Native Companion",
    version=__version__,
    docs_url="/docs",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> dict[str, Any]:
    state = database.health()
    return {
        **state,
        "outbox_worker": "active" if settings.n8n_webhook_url else "disabled",
        "n8n_configured": settings.n8n_webhook_url is not None,
        "version": __version__,
    }


@app.post("/v1/events", status_code=202)
async def receive_event(event: EventEnvelope) -> dict[str, bool]:
    record = event.database_record()
    created = database.record_event(record, enqueue_external=True)
    return {"accepted": True, "duplicate": not created}
