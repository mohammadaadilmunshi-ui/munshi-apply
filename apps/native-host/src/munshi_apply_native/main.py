from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import __version__
from .application_plan_handoff_v2 import ApplicationPlanHandoffConsumer
from .complete_application_loop import CompleteApplicationLoopService
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


class StartLoopSessionRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=240)


class ResolveLoopTaskRequest(BaseModel):
    value: Any
    approved_by_user: bool = True


def _loop_service(
    x_munshi_command_secret: str | None = Header(default=None),
    x_munshi_tenant_id: str | None = Header(default=None),
    x_munshi_user_id: str | None = Header(default=None),
) -> CompleteApplicationLoopService:
    """Default-off local command boundary; the caller chooses no authority."""
    configured = settings.command_secret
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Loop commands are disabled"
        )
    if not x_munshi_command_secret or not secrets.compare_digest(
        x_munshi_command_secret, configured
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid loop command secret"
        )
    tenant_id = str(x_munshi_tenant_id or "").strip()
    user_id = str(x_munshi_user_id or "").strip()
    if not tenant_id or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Execution owner headers are required",
        )
    return CompleteApplicationLoopService(database, tenant_id=tenant_id, user_id=user_id)


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


@app.post("/v1/application-plan-handoffs", status_code=202)
async def accept_application_plan_handoff(request: Request) -> dict[str, Any]:
    # Authenticate and persist one Hunter Application Plan V2; never execute it.
    bridge_secret = settings.handoff_hmac_secret
    if not bridge_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application Plan handoff is disabled",
        )

    body = await request.body()
    consumer = ApplicationPlanHandoffConsumer(
        database,
        bridge_secret=bridge_secret,
    )
    result = consumer.accept(body, dict(request.headers))
    if not result.accepted:
        if result.error == "live handoff disabled":
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif result.error == "invalid signature":
            status_code = status.HTTP_401_UNAUTHORIZED
        else:
            status_code = status.HTTP_409_CONFLICT
        raise HTTPException(
            status_code=status_code,
            detail=result.error or "Application Plan handoff rejected",
        )
    return result.__dict__


@app.post("/v1/complete-loop/sessions")
def start_complete_loop_session(
    request: StartLoopSessionRequest,
    service: CompleteApplicationLoopService = Depends(_loop_service),  # noqa: B008
) -> dict[str, Any]:
    try:
        result = service.start_session(plan_id=request.plan_id)
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return result.__dict__


@app.post("/v1/complete-loop/reviews/{review_id}/approve")
def approve_complete_loop_review(
    review_id: str,
    service: CompleteApplicationLoopService = Depends(_loop_service),  # noqa: B008
) -> dict[str, Any]:
    try:
        return service.approve_review(review_id=review_id)
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@app.post("/v1/complete-loop/tasks/{task_id}/resolve")
def resolve_complete_loop_task(
    task_id: str,
    request: ResolveLoopTaskRequest,
    service: CompleteApplicationLoopService = Depends(_loop_service),  # noqa: B008
) -> dict[str, Any]:
    try:
        return service.resolve_task(
            task_id=task_id, value=request.value, approved_by_user=request.approved_by_user
        )
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
