from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import __version__
from .application_plan_handoff_v2 import ApplicationPlanHandoffConsumer
from .background_prepare_queue import DurablePreparationQueue
from .complete_application_loop import CompleteApplicationLoopService
from .database import Database
from .models import EventEnvelope, HealthResponse
from .outbox import OutboxWorker, run_outbox_worker
from .runtime_resolution_read_v1 import RuntimeResolutionReadModel
from .settings import Settings
from .teach_munshi_telegram import (
    TeachMunshiTelegramWorker,
    run_teach_munshi_telegram_worker,
)
from .teach_munshi_worker import (
    TeachMunshiLearningWorker,
    run_teach_munshi_learning_worker,
)

settings = Settings.from_environment()
database = Database(settings.database_path, settings.migrations_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.migrate()
    stop_event = asyncio.Event()
    worker_tasks: list[asyncio.Task[None]] = []

    # Teach MUNSHI learning is always local/deterministic at this stage. The
    # browser only inserts a verified, value-free lesson; this background worker
    # turns that lesson into SHADOW/promoted recipe evidence without delaying the
    # application path or making any AI provider call.
    teach_learning_worker = TeachMunshiLearningWorker(database)
    worker_tasks.append(
        asyncio.create_task(
            run_teach_munshi_learning_worker(
                teach_learning_worker,
                stop_event,
            )
        )
    )

    if settings.n8n_webhook_url and settings.n8n_webhook_secret:
        worker = OutboxWorker(
            database,
            settings.n8n_webhook_url,
            settings.n8n_webhook_secret,
        )
        worker_tasks.append(
            asyncio.create_task(
                run_outbox_worker(
                    worker,
                    stop_event,
                    poll_seconds=settings.outbox_poll_seconds,
                )
            )
        )

    if settings.teach_telegram_bot_token and settings.teach_telegram_chat_id:
        teach_worker = TeachMunshiTelegramWorker(
            database,
            settings.teach_telegram_bot_token,
            settings.teach_telegram_chat_id,
        )
        worker_tasks.append(
            asyncio.create_task(
                run_teach_munshi_telegram_worker(
                    teach_worker,
                    stop_event,
                    poll_seconds=settings.teach_telegram_poll_seconds,
                )
            )
        )

    yield

    if worker_tasks:
        stop_event.set()
        await asyncio.gather(*worker_tasks)


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


class HealthResponseWithTeach(HealthResponse):
    teach_learning_worker: str
    teach_telegram_worker: str
    teach_telegram_configured: bool


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


@app.get("/health", response_model=HealthResponseWithTeach)
def health() -> dict[str, Any]:
    state = database.health()
    teach_telegram_configured = bool(
        settings.teach_telegram_bot_token and settings.teach_telegram_chat_id
    )
    return {
        **state,
        "outbox_worker": "active" if settings.n8n_webhook_url else "disabled",
        "n8n_configured": settings.n8n_webhook_url is not None,
        "teach_learning_worker": "active",
        "teach_telegram_worker": "active" if teach_telegram_configured else "disabled",
        "teach_telegram_configured": teach_telegram_configured,
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
        if result.error in {"live handoff disabled", "plan supersession disabled"}:
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
        preparation_job = DurablePreparationQueue(database).enqueue_session(
            session_id=result.session_id,
            tenant_id=service.tenant_id,
            user_id=service.user_id,
        )
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {**result.__dict__, "preparation_job": preparation_job}


@app.post("/v1/complete-loop/sessions/{session_id}/review")
def freeze_complete_loop_review(
    session_id: str,
    service: CompleteApplicationLoopService = Depends(_loop_service),  # noqa: B008
) -> dict[str, Any]:
    """Freeze the prepared state for Hunter's single customer review."""
    try:
        return service.build_review(session_id=session_id)
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


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
    _ = (task_id, request, service)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Runtime NEEDS_INPUT resolution requires a Hunter-authorized "
            "replacement Application Plan."
        ),
    )


# Phase 1C-A durable preparation job API


@app.get("/v1/complete-loop/preparation-jobs/{job_id}")
def get_complete_loop_preparation_job(
    job_id: str,
    service: CompleteApplicationLoopService = Depends(_loop_service),  # noqa: B008
) -> dict[str, Any]:
    try:
        return DurablePreparationQueue(database).get(
            job_id=job_id,
            tenant_id=service.tenant_id,
            user_id=service.user_id,
        )
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@app.get("/v1/complete-loop/preparation-jobs/{job_id}/resolution-tasks")
def get_complete_loop_resolution_tasks(
    job_id: str,
    service: CompleteApplicationLoopService = Depends(_loop_service),  # noqa: B008
) -> dict[str, Any]:
    """Read-only owner-scoped runtime question metadata for Hunter."""
    try:
        return RuntimeResolutionReadModel(database).for_prepare_job(
            job_id=job_id,
            tenant_id=service.tenant_id,
            user_id=service.user_id,
        )
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@app.post("/v1/complete-loop/preparation-jobs/{job_id}/cancel")
def cancel_complete_loop_preparation_job(
    job_id: str,
    service: CompleteApplicationLoopService = Depends(_loop_service),  # noqa: B008
) -> dict[str, Any]:
    try:
        return DurablePreparationQueue(database).request_cancel(
            job_id=job_id,
            tenant_id=service.tenant_id,
            user_id=service.user_id,
        )
    except (LookupError, PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
