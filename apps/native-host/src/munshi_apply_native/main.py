from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from . import __version__
from .database import Database
from .models import EventEnvelope, HealthResponse
from .n8n import forward_event
from .settings import Settings

settings = Settings.from_environment()
database = Database(settings.database_path, settings.migrations_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.migrate()
    yield


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
        "n8n_configured": settings.n8n_webhook_url is not None,
        "version": __version__,
    }


@app.post("/v1/events", status_code=202)
async def receive_event(event: EventEnvelope) -> dict[str, bool]:
    record = event.database_record()
    database.append_event(record)
    if settings.n8n_webhook_url:
        await asyncio.to_thread(
            forward_event,
            settings.n8n_webhook_url,
            event.model_dump(by_alias=True, mode="json"),
            settings.n8n_webhook_secret,
        )
    return {"accepted": True}
