"""Trust-aware hosted preparation entrypoint.

Security challenges are never solved or bypassed. When a challenge appears, the
worker parks the exact Playwright context instead of treating the application as
terminally blocked. The job enters WAITING_INPUT while the same live browser is
retained in-process. Automation resumes only after that exact browser no longer
shows the challenge and the exact application is revalidated.

A worker restart deliberately loses the live-browser capability and therefore
cannot clear the durable checkpoint. That failure mode remains fail-closed.
"""

from __future__ import annotations

import os
import socket
import time
from contextlib import suppress
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from .background_prepare_queue import DurablePreparationQueue
from .complete_application_loop import (
    BACKGROUND_PREPARE_ENV,
    CompleteApplicationLoopService,
)
from .database import Database
from .hosted_prepare_worker import (
    BRIDGE_URL_ENV,
    HOSTED_WORKER_ENV,
    NORMAL_AUTOFILL_ENV,
    RESUME_UPLOAD_ENV,
    HostedAdapterFactory,
    HostedPreparationRunner,
    _boolean_value,
    _truthy,
    browser_runtime_self_check,
)
from .settings import Settings
from .trust_checkpoint_store import TrustCheckpointStore


class UserAuthRequired(RuntimeError):
    """Internal control signal for a detected legitimate browser trust boundary."""

    def __init__(self, checkpoint: dict[str, Any]) -> None:
        super().__init__("Browser security checkpoint requires user authentication")
        self.checkpoint = dict(checkpoint)


class TrustAwareHostedPlanBrowserAdapter:
    """Composition wrapper that can retain one live browser across a checkpoint."""

    def __init__(
        self,
        delegate: Any,
        *,
        trust_checkpoints: TrustCheckpointStore,
        job: dict[str, Any],
        on_park: Any = None,
    ) -> None:
        self._delegate = delegate
        self._trust_checkpoints = trust_checkpoints
        self._job = dict(job)
        self._on_park = on_park
        self._active_checkpoint: dict[str, Any] | None = None
        self._plan: dict[str, Any] | None = None
        self._parked = False
        self._resume_ready = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    @property
    def job_id(self) -> str:
        return str(self._job["job_id"])

    @property
    def resume_ready(self) -> bool:
        return self._resume_ready

    def _remember_plan(self, plan: dict[str, Any]) -> None:
        self._plan = dict(plan)

    def _observe_security(
        self,
        observation: dict[str, Any],
    ) -> dict[str, Any] | None:
        kind = observation.get("security_checkpoint")
        if not kind:
            return None
        checkpoint = self._trust_checkpoints.observe(
            job_id=self.job_id,
            tenant_id=str(self._job["tenant_id"]),
            user_id=str(self._job["user_id"]),
            checkpoint_kind=kind,
            current_url=str(observation.get("current_url") or ""),
            page_fingerprint=str(
                observation.get("page_fingerprint") or "unknown"
            ),
        )
        self._active_checkpoint = checkpoint
        return checkpoint

    def inspect_job(self, *, plan: dict[str, Any]) -> dict[str, Any]:
        self._remember_plan(plan)
        observation = self._delegate.inspect_job(plan=plan)
        trust = self._observe_security(observation)
        if trust is not None:
            raise UserAuthRequired(trust)
        return observation

    def prepare_form(
        self,
        *,
        plan: dict[str, Any],
        checkpoint: dict[str, Any] | None,
        resolved_values: dict[str, Any],
    ) -> dict[str, Any]:
        self._remember_plan(plan)
        try:
            return self._delegate.prepare_form(
                plan=plan,
                checkpoint=checkpoint,
                resolved_values=resolved_values,
            )
        except ValueError as error:
            expected = "Browser identity or security checkpoint blocks preparation"
            if expected not in str(error):
                raise
            observation = self._delegate.inspect_job(plan=plan)
            trust = self._observe_security(observation)
            if trust is None:
                raise
            raise UserAuthRequired(trust) from error

    def active_trust_checkpoint(self) -> dict[str, Any] | None:
        if self._active_checkpoint is not None:
            return dict(self._active_checkpoint)
        return self._trust_checkpoints.active_for_job(
            job_id=self.job_id,
            tenant_id=str(self._job["tenant_id"]),
            user_id=str(self._job["user_id"]),
        )

    def park_for_user_auth(self, checkpoint: dict[str, Any]) -> None:
        active = self.active_trust_checkpoint()
        if active is None:
            raise RuntimeError("Cannot park without an active trust checkpoint")
        if (
            str(active["trust_checkpoint_id"])
            != str(checkpoint["trust_checkpoint_id"])
        ):
            raise RuntimeError("Trust checkpoint changed before browser park")
        self._parked = True
        self._resume_ready = False
        if callable(self._on_park):
            self._on_park(self)

    def _navigate_back_to_application(self) -> None:
        if self._plan is None:
            return
        target = str(
            dict(self._plan.get("job") or {}).get("apply_url")
            or dict(self._plan.get("job") or {}).get("job_url")
            or ""
        )
        page = getattr(self._delegate, "page", None)
        if not target or page is None:
            return
        with suppress(Exception):
            if str(getattr(page, "url", "") or "") != target:
                page.goto(target, wait_until="domcontentloaded")

    def live_revalidation(self) -> dict[str, Any] | None:
        """Return a safe observation only when this retained browser can resume."""
        if not self._parked or self._resume_ready or self._plan is None:
            return None
        try:
            observation = self._delegate.inspect_job(plan=self._plan)
        except Exception:
            return None
        if observation.get("security_checkpoint"):
            return None

        expected_job_id = str(dict(self._plan.get("job") or {}).get("id") or "")
        if str(observation.get("job_id") or "") != expected_job_id:
            self._navigate_back_to_application()
            try:
                observation = self._delegate.inspect_job(plan=self._plan)
            except Exception:
                return None
        if observation.get("security_checkpoint"):
            return None
        if str(observation.get("job_id") or "") != expected_job_id:
            return None
        if not observation.get("current_url"):
            return None
        return dict(observation)

    def mark_resume_ready(self) -> None:
        if not self._parked:
            raise RuntimeError("Only a parked browser can become resume-ready")
        self._resume_ready = True

    def resume_from_park(self) -> None:
        if not self._resume_ready:
            raise RuntimeError("Parked browser has not been revalidated")
        self._parked = False
        self._resume_ready = False
        self._active_checkpoint = None

    def close(self) -> None:
        if self._parked:
            return
        close = getattr(self._delegate, "close", None)
        if callable(close):
            close()


class TrustAwareAdapterFactory:
    """Own retained browser capabilities and requeue only after live revalidation."""

    def __init__(
        self,
        base_factory: Any,
        trust_checkpoints: TrustCheckpointStore,
    ) -> None:
        self._base_factory = base_factory
        self._trust_checkpoints = trust_checkpoints
        self._parked: dict[str, TrustAwareHostedPlanBrowserAdapter] = {}

    def _register_parked(
        self,
        adapter: TrustAwareHostedPlanBrowserAdapter,
    ) -> None:
        previous = self._parked.get(adapter.job_id)
        if previous is not None and previous is not adapter:
            raise RuntimeError("A different live browser is already parked for this job")
        self._parked[adapter.job_id] = adapter

    def __call__(
        self,
        job: dict[str, Any],
    ) -> TrustAwareHostedPlanBrowserAdapter:
        job_id = str(job["job_id"])
        retained = self._parked.get(job_id)
        if retained is not None and retained.resume_ready:
            self._parked.pop(job_id, None)
            retained.resume_from_park()
            return retained
        return TrustAwareHostedPlanBrowserAdapter(
            self._base_factory(job),
            trust_checkpoints=self._trust_checkpoints,
            job=job,
            on_park=self._register_parked,
        )

    def resume_ready_checkpoints(self) -> int:
        resumed = 0
        for _job_id, adapter in tuple(self._parked.items()):
            observation = adapter.live_revalidation()
            if observation is None:
                continue
            checkpoint = adapter.active_trust_checkpoint()
            if checkpoint is None:
                continue
            cleared = (
                self._trust_checkpoints.clear_after_live_browser_revalidation(
                    trust_checkpoint_id=str(
                        checkpoint["trust_checkpoint_id"]
                    ),
                    tenant_id=str(adapter._job["tenant_id"]),
                    user_id=str(adapter._job["user_id"]),
                    current_url=str(observation["current_url"]),
                    page_fingerprint=str(
                        observation.get("page_fingerprint") or "unknown"
                    ),
                )
            )
            if str(cleared.get("prepare_job_state")) != "QUEUED":
                raise RuntimeError(
                    "Live browser revalidated but preparation was not requeued"
                )
            adapter.mark_resume_ready()
            resumed += 1
        return resumed


class TrustAwareCompleteApplicationLoopService:
    """Service proxy that maps browser trust challenges to a resumable queue wait."""

    def __init__(
        self,
        delegate: CompleteApplicationLoopService,
        *,
        trust_checkpoints: TrustCheckpointStore,
        job: dict[str, Any],
    ) -> None:
        self._delegate = delegate
        self._trust_checkpoints = trust_checkpoints
        self._job = dict(job)

    def preflight_prepare_session(self, session_id: str) -> None:
        self._delegate.preflight_prepare_session(session_id)

    def prepare_session(self, *, session_id: str, adapter: Any) -> Any:
        try:
            return self._delegate.prepare_session(
                session_id=session_id,
                adapter=adapter,
            )
        except UserAuthRequired as signal:
            self._trust_checkpoints.record_waiting_for_user_auth(
                trust_checkpoint_id=str(
                    signal.checkpoint["trust_checkpoint_id"]
                ),
                tenant_id=str(self._job["tenant_id"]),
                user_id=str(self._job["user_id"]),
            )
            park = getattr(adapter, "park_for_user_auth", None)
            if callable(park):
                park(signal.checkpoint)
            return SimpleNamespace(state="NEEDS_INPUT")


class TrustAwareHostedPreparationRunner(HostedPreparationRunner):
    """Poll retained live browsers before claiming ordinary queued work."""

    def __init__(
        self,
        *args: Any,
        trust_adapter_factory: TrustAwareAdapterFactory,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._trust_adapter_factory = trust_adapter_factory

    def run_once(self, *, worker_id: str) -> Any:
        self._trust_adapter_factory.resume_ready_checkpoints()
        return super().run_once(worker_id=worker_id)


def build_runner(
    database: Database,
    settings: Settings,
) -> HostedPreparationRunner:
    """Build the hosted runner with live-browser trust checkpoint retention."""
    if not settings.handoff_hmac_secret:
        raise RuntimeError(
            "Apply handoff HMAC secret is required for hosted preparation"
        )
    bridge_url = str(os.getenv(BRIDGE_URL_ENV) or "").strip()
    if not bridge_url:
        raise RuntimeError("Hunter execution bridge base URL is required")

    queue = DurablePreparationQueue(database)
    trust_checkpoints = TrustCheckpointStore(database)
    base_factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url=bridge_url,
        bridge_secret=settings.handoff_hmac_secret,
        browser_executable=os.getenv("MUNSHI_BROWSER_EXECUTABLE") or None,
        navigation_timeout_ms=int(
            os.getenv("MUNSHI_APPLY_BROWSER_TIMEOUT_MS", "30000")
        ),
        headless=_boolean_value(
            os.getenv("MUNSHI_APPLY_BROWSER_HEADLESS"),
            default=True,
        ),
    )
    adapter_factory = TrustAwareAdapterFactory(
        base_factory,
        trust_checkpoints,
    )

    def service_factory(
        job: dict[str, Any],
    ) -> TrustAwareCompleteApplicationLoopService:
        return TrustAwareCompleteApplicationLoopService(
            CompleteApplicationLoopService(
                database,
                tenant_id=str(job["tenant_id"]),
                user_id=str(job["user_id"]),
            ),
            trust_checkpoints=trust_checkpoints,
            job=job,
        )

    return TrustAwareHostedPreparationRunner(
        queue,
        service_factory=service_factory,
        adapter_factory=adapter_factory,
        trust_adapter_factory=adapter_factory,
        lease_seconds=int(
            os.getenv("MUNSHI_APPLY_PREPARE_LEASE_SECONDS", "300")
        ),
    )


def run_forever() -> None:
    if not _truthy(BACKGROUND_PREPARE_ENV):
        raise RuntimeError("Apply background preparation is disabled")
    if not _truthy(HOSTED_WORKER_ENV):
        raise RuntimeError("Hosted Apply preparation worker is disabled")
    if not _truthy(RESUME_UPLOAD_ENV) or not _truthy(NORMAL_AUTOFILL_ENV):
        raise RuntimeError(
            "Hosted resume upload and normal answer autofill are disabled"
        )

    settings = Settings.from_environment()
    database = Database(settings.database_path, settings.migrations_path)
    database.migrate()
    browser_runtime_self_check(
        browser_executable=os.getenv("MUNSHI_BROWSER_EXECUTABLE") or None,
        headless=_boolean_value(
            os.getenv("MUNSHI_APPLY_BROWSER_HEADLESS"),
            default=True,
        ),
    )
    runner = build_runner(database, settings)
    worker_id = str(
        os.getenv("MUNSHI_APPLY_PREPARE_WORKER_ID")
        or f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
    )
    poll = max(
        0.1,
        min(
            30.0,
            float(os.getenv("MUNSHI_APPLY_PREPARE_POLL_SECONDS", "1")),
        ),
    )
    while True:
        result = runner.run_once(worker_id=worker_id)
        if result is None:
            time.sleep(poll)


def main() -> int:
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
