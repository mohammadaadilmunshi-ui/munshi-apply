"""Trust-aware hosted preparation entrypoint.

This module layers durable user-auth checkpoints over the proven hosted worker
without changing its heartbeat, lease, retry, artifact-integrity, or browser
lifecycle implementation. Security challenges are never solved or bypassed.
They release the worker into the existing non-claimable WAITING_INPUT queue
backing state while the sidecar exposes WAITING_FOR_USER_AUTH.
"""

from __future__ import annotations

import os
import socket
import time
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from .background_prepare_queue import DurablePreparationQueue
from .complete_application_loop import BACKGROUND_PREPARE_ENV, CompleteApplicationLoopService
from .database import Database
from .hosted_prepare_worker import (
    BRIDGE_URL_ENV,
    HOSTED_WORKER_ENV,
    NORMAL_AUTOFILL_ENV,
    RESUME_UPLOAD_ENV,
    STAGING_HTTP_ENV,
    HostedAdapterFactory,
    HostedPreparationRunner,
    _truthy,
)
from .settings import Settings
from .trust_checkpoint_store import TrustCheckpointStore


class UserAuthRequired(RuntimeError):
    """Internal control signal for a detected legitimate browser trust boundary."""

    def __init__(self, checkpoint: dict[str, Any]) -> None:
        super().__init__("Browser security checkpoint requires user authentication")
        self.checkpoint = dict(checkpoint)


class TrustAwareHostedPlanBrowserAdapter:
    """Composition wrapper that persists security checkpoints without secrets."""

    def __init__(
        self,
        delegate: Any,
        *,
        trust_checkpoints: TrustCheckpointStore,
        job: dict[str, Any],
    ) -> None:
        self._delegate = delegate
        self._trust_checkpoints = trust_checkpoints
        self._job = dict(job)
        self._active_checkpoint: dict[str, Any] | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def _observe_security(self, observation: dict[str, Any]) -> dict[str, Any] | None:
        kind = observation.get("security_checkpoint")
        if not kind:
            return None
        checkpoint = self._trust_checkpoints.observe(
            job_id=str(self._job["job_id"]),
            tenant_id=str(self._job["tenant_id"]),
            user_id=str(self._job["user_id"]),
            checkpoint_kind=kind,
            current_url=str(observation.get("current_url") or ""),
            page_fingerprint=str(observation.get("page_fingerprint") or "unknown"),
        )
        self._active_checkpoint = checkpoint
        return checkpoint

    def inspect_job(self, *, plan: dict[str, Any]) -> dict[str, Any]:
        observation = self._delegate.inspect_job(plan=plan)
        trust = self._observe_security(observation)
        if trust is not None:
            # Stop before CompleteApplicationLoopService can convert this legitimate
            # security boundary into its generic terminal BLOCKED state.
            raise UserAuthRequired(trust)
        return observation

    def prepare_form(
        self,
        *,
        plan: dict[str, Any],
        checkpoint: dict[str, Any] | None,
        resolved_values: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self._delegate.prepare_form(
                plan=plan,
                checkpoint=checkpoint,
                resolved_values=resolved_values,
            )
        except ValueError as error:
            if "Browser identity or security checkpoint blocks preparation" not in str(error):
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
            job_id=str(self._job["job_id"]),
            tenant_id=str(self._job["tenant_id"]),
            user_id=str(self._job["user_id"]),
        )

    def close(self) -> None:
        close = getattr(self._delegate, "close", None)
        if callable(close):
            close()


class TrustAwareAdapterFactory:
    def __init__(self, base_factory: Any, trust_checkpoints: TrustCheckpointStore) -> None:
        self._base_factory = base_factory
        self._trust_checkpoints = trust_checkpoints

    def __call__(self, job: dict[str, Any]) -> TrustAwareHostedPlanBrowserAdapter:
        return TrustAwareHostedPlanBrowserAdapter(
            self._base_factory(job),
            trust_checkpoints=self._trust_checkpoints,
            job=job,
        )


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
            return self._delegate.prepare_session(session_id=session_id, adapter=adapter)
        except UserAuthRequired as signal:
            self._trust_checkpoints.record_waiting_for_user_auth(
                trust_checkpoint_id=str(signal.checkpoint["trust_checkpoint_id"]),
                tenant_id=str(self._job["tenant_id"]),
                user_id=str(self._job["user_id"]),
            )
            # HostedPreparationRunner already maps NEEDS_INPUT to WAITING_INPUT,
            # releases its lease, closes the browser, and continues other jobs.
            # The authoritative session/application state is intentionally preserved.
            return SimpleNamespace(state="NEEDS_INPUT")


def build_runner(database: Database, settings: Settings) -> HostedPreparationRunner:
    """Build the proven hosted runner with trust-aware wrappers only."""
    if not settings.handoff_hmac_secret:
        raise RuntimeError("Apply handoff HMAC secret is required for hosted preparation")
    bridge_url = str(os.getenv(BRIDGE_URL_ENV) or "").strip()
    if not bridge_url:
        raise RuntimeError("Hunter execution bridge base URL is required")
    allow_staging_http = _truthy(STAGING_HTTP_ENV)
    if allow_staging_http and str(os.getenv("MUNSHI_ENVIRONMENT") or "").casefold() != "staging":
        raise RuntimeError("Hunter bridge staging HTTP is restricted to staging")

    queue = DurablePreparationQueue(database)
    trust_checkpoints = TrustCheckpointStore(database)
    base_factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url=bridge_url,
        bridge_secret=settings.handoff_hmac_secret,
        allow_staging_http=allow_staging_http,
        browser_executable=os.getenv("MUNSHI_BROWSER_EXECUTABLE") or None,
        navigation_timeout_ms=int(os.getenv("MUNSHI_APPLY_BROWSER_TIMEOUT_MS", "30000")),
    )
    adapter_factory = TrustAwareAdapterFactory(base_factory, trust_checkpoints)

    def service_factory(job: dict[str, Any]) -> TrustAwareCompleteApplicationLoopService:
        return TrustAwareCompleteApplicationLoopService(
            CompleteApplicationLoopService(
                database,
                tenant_id=str(job["tenant_id"]),
                user_id=str(job["user_id"]),
            ),
            trust_checkpoints=trust_checkpoints,
            job=job,
        )

    return HostedPreparationRunner(
        queue,
        service_factory=service_factory,
        adapter_factory=adapter_factory,
        lease_seconds=int(os.getenv("MUNSHI_APPLY_PREPARE_LEASE_SECONDS", "300")),
    )


def run_forever() -> None:
    if not _truthy(BACKGROUND_PREPARE_ENV):
        raise RuntimeError("Apply background preparation is disabled")
    if not _truthy(HOSTED_WORKER_ENV):
        raise RuntimeError("Hosted Apply preparation worker is disabled")
    if not _truthy(RESUME_UPLOAD_ENV) or not _truthy(NORMAL_AUTOFILL_ENV):
        raise RuntimeError("Hosted resume upload and normal answer autofill are disabled")

    settings = Settings.from_environment()
    database = Database(settings.database_path, settings.migrations_path)
    database.migrate()
    runner = build_runner(database, settings)
    worker_id = str(
        os.getenv("MUNSHI_APPLY_PREPARE_WORKER_ID")
        or f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
    )
    poll = max(0.1, min(30.0, float(os.getenv("MUNSHI_APPLY_PREPARE_POLL_SECONDS", "1"))))
    while True:
        result = runner.run_once(worker_id=worker_id)
        if result is None:
            time.sleep(poll)


def main() -> int:
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
