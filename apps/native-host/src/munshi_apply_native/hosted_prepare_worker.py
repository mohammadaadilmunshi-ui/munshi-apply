"""Hosted pre-submit Chromium worker for the Complete Application Loop.

This worker may navigate, inspect, upload the exact immutable resume, fill
normal approved answers, persist checkpoints, and stop at NEEDS_INPUT or
READY_FOR_REVIEW. It contains no final-review or submit call.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import sync_playwright

from .account_store import AccountStore, portal_identity
from .account_teach_service import AccountTeachService
from .artifact_fetch_v2 import HunterExecutionBridgeClient
from .background_prepare_queue import DurablePreparationQueue, PreparationRunResult
from .browser_runtime import resolve_browser_executable
from .complete_application_loop import BACKGROUND_PREPARE_ENV, CompleteApplicationLoopService
from .database import Database
from .execution_policy import prepare_permissions
from .hosted_account_orchestrator import HostedAccountOrchestrator
from .hosted_account_session import HostedAccountSessionStore
from .hosted_interaction_recovery import HostedRecoveringPlanBrowserAdapter
from .interaction_fallback_service import InteractionFallbackService
from .settings import Settings
from .teach_munshi_service import TeachMunshiService

HOSTED_WORKER_ENV = "MUNSHI_APPLY_HOSTED_PREPARE_WORKER_ENABLED"
BRIDGE_URL_ENV = "MUNSHI_HUNTER_EXECUTION_BRIDGE_BASE_URL"
RESUME_UPLOAD_ENV = "MUNSHI_APPLY_RESUME_UPLOAD_ENABLED"
NORMAL_AUTOFILL_ENV = "MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED"
BROWSER_HEALTH_PATH_ENV = "MUNSHI_APPLY_BROWSER_HEALTH_PATH"


def _truthy(name: str) -> bool:
    return str(os.getenv(name) or "").strip().casefold() in {"1", "true", "yes", "on"}


def _boolean_value(value: Any, *, default: bool = False) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _record_browser_health(payload: dict[str, Any], path: str | Path | None) -> None:
    safe = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    print(f"BROWSER_RUNTIME_SELF_CHECK {safe}", flush=True)
    if path is None:
        return
    target = Path(path)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(safe + "\n", encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        with suppress(OSError):
            temporary.unlink()


def browser_runtime_self_check(
    *,
    browser_executable: str | None = None,
    headless: bool = True,
    playwright_factory: Any = sync_playwright,
    health_path: str | Path | None = None,
) -> dict[str, Any]:
    """Prove the configured Chromium can launch without visiting any website."""
    executable = resolve_browser_executable(browser_executable)
    target_path = health_path
    if target_path is None:
        target_path = os.getenv(BROWSER_HEALTH_PATH_ENV, "/data/browser-runtime-health.json")
    status: dict[str, Any] = {
        "status": "DEGRADED",
        "checked_at": datetime.now(UTC).isoformat(),
        "headless": bool(headless),
        "executable": executable,
    }
    pw = browser = context = None
    try:
        pw = playwright_factory().start()
        browser = pw.chromium.launch(
            headless=bool(headless),
            executable_path=executable,
        )
        context = browser.new_context()
        page = context.new_page()
        page.set_content("<!doctype html><title>MUNSHI browser ready</title>")
        if page.title() != "MUNSHI browser ready":
            raise RuntimeError("Chromium page readiness probe returned an unexpected title")
        status["status"] = "PASS"
    except Exception as error:
        status["error_type"] = type(error).__name__
        status["message"] = "Chromium could not launch with the configured production mode."
        _record_browser_health(status, target_path)
        raise RuntimeError(status["message"]) from error
    finally:
        if context is not None:
            with suppress(Exception):
                context.close()
        if browser is not None:
            with suppress(Exception):
                browser.close()
        if pw is not None:
            with suppress(Exception):
                pw.stop()
    _record_browser_health(status, target_path)
    return status


def _runtime_path() -> Path:
    path = Path(__file__).resolve().parents[2] / "browser-dist/plan-runtime.js"
    if not path.is_file():
        raise RuntimeError("Compiled PlanBrowser runtime is missing")
    return path


def _target_url(plan: dict[str, Any]) -> str:
    job = dict(plan["job"])
    policy = dict(plan["provider_policy"])
    target = str(job.get("apply_url") or job.get("job_url") or "").strip()
    parsed = urlsplit(target)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Application target URL is not a safe HTTPS destination")
    allowed = [str(value).casefold().rstrip(".") for value in policy.get("allowed_hosts") or []]
    if allowed and not any(host == suffix or host.endswith("." + suffix) for suffix in allowed):
        raise ValueError("Application target host is outside provider policy")
    if plan.get("submission_authority") is not False:
        raise ValueError("Background worker cannot accept submission authority")
    return target


def _enter_workday_application_surface(
    page: Any,
    *,
    plan: dict[str, Any],
    navigation_timeout_ms: int,
) -> bool:
    """Reach Workday's account/application surface without choosing an answer.

    Workday exposes a job-details shell first, then a job-bound ``/apply`` route,
    then a choice such as ``Autofill with Resume``.  Account orchestration must
    run after those reversible entry actions because the login/create-account
    form does not exist on the public job shell.
    """

    provider = str(dict(plan.get("provider_policy") or {}).get("provider") or "")
    if provider.strip().upper() != "WORKDAY":
        return False

    target = _target_url(plan)
    expected = urlsplit(target)
    entered = False
    deadline = time.monotonic() + min(10.0, max(2.0, navigation_timeout_ms / 1000.0))
    apply_href = ""
    while time.monotonic() < deadline:
        try:
            apply_href = str(
                page.evaluate(
                    r"""() => {
                      const visible = element => {
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.display !== 'none'
                          && style.visibility !== 'hidden'
                          && Number(style.opacity || 1) !== 0
                          && rect.width > 0 && rect.height > 0;
                      };
                      const label = element => String(
                        element.innerText || element.getAttribute('aria-label') || ''
                      ).replace(/\s+/g, ' ').trim().toLowerCase();
                      const candidates = Array.from(document.querySelectorAll('a[href]'))
                        .filter(element => visible(element) && label(element) === 'apply');
                      return candidates.length === 1 ? candidates[0].href : '';
                    }"""
                )
                or ""
            )
        except Exception:
            apply_href = ""
        if apply_href:
            break
        page.wait_for_timeout(100)

    if apply_href:
        destination = urlsplit(apply_href)
        expected_path = expected.path.rstrip("/")
        if not (
            destination.scheme == expected.scheme
            and destination.netloc == expected.netloc
            and destination.path == expected_path + "/apply"
            and not destination.username
            and not destination.password
            and not destination.fragment
        ):
            raise ValueError("Workday application entry left the exact job binding")
        page.goto(
            apply_href,
            wait_until="domcontentloaded",
            timeout=navigation_timeout_ms,
        )
        entered = True

    current = urlsplit(str(page.url))
    if current.path != expected.path.rstrip("/") + "/apply":
        return entered

    deadline = time.monotonic() + min(10.0, max(2.0, navigation_timeout_ms / 1000.0))
    while time.monotonic() < deadline:
        choice = page.evaluate(
            r"""() => {
              const visible = element => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && Number(style.opacity || 1) !== 0
                  && rect.width > 0 && rect.height > 0;
              };
              const label = element => String(
                element.innerText || element.value
                || element.getAttribute('aria-label') || ''
              ).replace(/\s+/g, ' ').trim().toLowerCase();
              const controls = Array.from(document.querySelectorAll(
                'button,[role="button"],a,input[type="button"]'
              )).filter(visible);
              for (const wanted of ['autofill with resume', 'apply manually']) {
                const matches = controls.filter(element => label(element) === wanted);
                if (matches.length === 1) {
                  matches[0].click();
                  return wanted;
                }
              }
              return '';
            }"""
        )
        if choice:
            page.wait_for_timeout(1800)
            return True
        page.wait_for_timeout(100)
    return entered


class HostedPlanBrowserAdapter(HostedRecoveringPlanBrowserAdapter):
    def __init__(
        self,
        *args: Any,
        playwright_instance: Any,
        browser: Any,
        context: Any,
        bridge: HunterExecutionBridgeClient,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._playwright_instance = playwright_instance
        self._browser = browser
        self._context = context
        self._bridge = bridge
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with suppress(Exception):
            self._context.close()
        with suppress(Exception):
            self._browser.close()
        with suppress(Exception):
            self._playwright_instance.stop()
        with suppress(Exception):
            self._bridge.close()


class HostedAdapterFactory:
    def __init__(
        self,
        database: Database,
        queue: DurablePreparationQueue,
        *,
        bridge_base_url: str,
        bridge_secret: str,
        browser_executable: str | None = None,
        navigation_timeout_ms: int = 30000,
        headless: bool = True,
        bridge_factory: Any = HunterExecutionBridgeClient,
        playwright_factory: Any = sync_playwright,
        context_configurer: Any = None,
        runtime_root: Path | None = None,
        interaction_fallback_service: Any = None,
        teach_munshi_service: Any = None,
        account_teach_service: Any = None,
    ) -> None:
        self.database = database
        self.queue = queue
        self.bridge_base_url = bridge_base_url
        self.bridge_secret = bridge_secret
        self.browser_executable = resolve_browser_executable(browser_executable)
        self.navigation_timeout_ms = int(navigation_timeout_ms)
        self.headless = bool(headless)
        self.bridge_factory = bridge_factory
        self.playwright_factory = playwright_factory
        self.context_configurer = context_configurer
        self.runtime_root = runtime_root
        self.interaction_fallback_service = interaction_fallback_service
        self.teach_munshi_service = teach_munshi_service or TeachMunshiService(database)
        self.account_teach_service = account_teach_service or AccountTeachService(database)

    def _plan(self, job: dict[str, Any]) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                (
                    "SELECT plan_json,plan_digest,tenant_id,user_id,application_id "
                    "FROM career_os_application_plans WHERE plan_id=?"
                ),
                (job["plan_id"],),
            ).fetchone()
        if row is None:
            raise LookupError("Hosted preparation plan was not found")
        if (
            str(row["tenant_id"]) != str(job["tenant_id"])
            or str(row["user_id"]) != str(job["user_id"])
            or str(row["application_id"]) != str(job["application_id"])
        ):
            raise PermissionError("Hosted preparation job owner binding is invalid")
        plan = json.loads(str(row["plan_json"]))
        from .application_plan_handoff_v2 import _plan_digest_payload, _sha256_json

        if _sha256_json(_plan_digest_payload(plan)) != str(row["plan_digest"]):
            raise ValueError("Hosted preparation plan digest binding is invalid")
        return plan

    def __call__(self, job: dict[str, Any]) -> HostedPlanBrowserAdapter:
        plan = self._plan(job)
        prepare_permissions(plan)
        target = _target_url(plan)
        bridge = self.bridge_factory(
            base_url=self.bridge_base_url,
            secret=self.bridge_secret,
            tenant_id=str(job["tenant_id"]),
            user_id=str(job["user_id"]),
        )
        if bridge.plan_is_current(plan) is not True:
            bridge.close()
            raise ValueError("Hosted preparation plan is stale")
        artifact = bridge.artifact_bytes(plan)
        expected_sha = str(plan["resume"]["artifact_sha256"])
        if hashlib.sha256(artifact).hexdigest() != expected_sha:
            bridge.close()
            raise RuntimeError("Hosted worker artifact digest verification failed")
        cover_letter: bytes | None = None
        cover_binding = (
            dict(plan["cover_letter"]) if isinstance(plan.get("cover_letter"), dict) else None
        )
        if cover_binding is not None:
            cover_letter = bridge.cover_letter_bytes(plan)
            if hashlib.sha256(cover_letter).hexdigest() != str(cover_binding["artifact_sha256"]):
                bridge.close()
                raise RuntimeError("Hosted worker cover-letter artifact digest verification failed")
        pw = browser = context = None
        try:
            pw = self.playwright_factory().start()
            browser = pw.chromium.launch(
                headless=self.headless,
                executable_path=self.browser_executable,
            )
            scope_key = portal_identity(target)[1]
            session_secret = (
                self.bridge_secret.encode("utf-8")
                if isinstance(self.bridge_secret, str)
                else bytes(self.bridge_secret)
            )
            session_store = HostedAccountSessionStore(
                self.database,
                bridge_secret=session_secret,
            )
            account_records = AccountStore(self.database).lookup({"portalUrl": target})
            expected_account_id = (
                str(account_records[0]["accountId"]) if len(account_records) == 1 else None
            )
            stored_state = (
                session_store.load(
                    tenant_id=str(job["tenant_id"]),
                    user_id=str(job["user_id"]),
                    scope_key=scope_key,
                    expected_account_id=expected_account_id,
                )
                if expected_account_id is not None
                else None
            )
            context_options: dict[str, Any] = {"accept_downloads": False}
            if stored_state is not None:
                context_options["storage_state"] = stored_state
            context = browser.new_context(**context_options)
            if self.context_configurer is not None:
                self.context_configurer(context, plan)
            page = context.new_page()
            page.set_default_timeout(self.navigation_timeout_ms)
            page.goto(target, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)

            _enter_workday_application_surface(
                page,
                plan=plan,
                navigation_timeout_ms=self.navigation_timeout_ms,
            )

            interaction_fallback = self.interaction_fallback_service
            if interaction_fallback is None and self.runtime_root is not None:
                # One Sonnet mechanics service is shared by account and application
                # preparation. It receives only structural metadata and opaque refs.
                interaction_fallback = InteractionFallbackService(
                    self.runtime_root,
                    config_resolver=lambda: bridge.autoapply_config(plan),
                    api_key_resolver=lambda: bridge.anthropic_api_key(plan),
                )

            # Account handling is part of preparation, not a separate/manual lane.
            # It runs in this exact context so login, create-account, email
            # verification, and the resumed application share one Chromium session.
            HostedAccountOrchestrator(
                self.database,
                plan=plan,
                bridge=bridge,
                page=page,
                context=context,
                tenant_id=str(job["tenant_id"]),
                user_id=str(job["user_id"]),
                session_secret=session_secret,
                interaction_fallback_service=interaction_fallback,
                teach_munshi_service=self.account_teach_service,
            ).run()

            def artifact_reader(current: dict[str, Any]) -> bytes:
                if str(current.get("plan_id")) != str(plan["plan_id"]) or str(
                    current.get("plan_digest")
                ) != str(plan["plan_digest"]):
                    raise ValueError("Browser artifact request no longer matches accepted plan")
                return artifact

            def cover_letter_reader(current: dict[str, Any]) -> bytes:
                if cover_letter is None or cover_binding is None:
                    raise ValueError("Accepted plan has no cover-letter artifact")
                if str(current.get("plan_id")) != str(plan["plan_id"]) or str(
                    current.get("plan_digest")
                ) != str(plan["plan_digest"]):
                    raise ValueError("Browser cover-letter request no longer matches accepted plan")
                return cover_letter

            def current_plan(current: dict[str, Any]) -> bool:
                queued = self.queue.get(
                    job_id=str(job["job_id"]),
                    tenant_id=str(job["tenant_id"]),
                    user_id=str(job["user_id"]),
                )
                if queued.get("cancel_requested_at") is not None:
                    return False
                if str(current.get("plan_id")) != str(plan["plan_id"]) or str(
                    current.get("plan_digest")
                ) != str(plan["plan_digest"]):
                    return False
                return bridge.plan_is_current(current)

            def protected_value_resolver(
                current: dict[str, Any],
                answer: dict[str, Any],
            ) -> dict[str, Any]:
                if str(current.get("plan_id")) != str(plan["plan_id"]) or str(
                    current.get("plan_digest")
                ) != str(plan["plan_digest"]):
                    raise ValueError(
                        "Protected browser value request no longer matches accepted plan"
                    )
                if bridge.plan_is_current(current) is not True:
                    raise ValueError(
                        "Protected browser value request belongs to a stale plan"
                    )
                question_key = str(answer.get("question_key") or "").strip()
                reference = str(answer.get("secure_resolver_ref") or "").strip()
                sensitivity = str(
                    answer.get("sensitivity_class") or ""
                ).strip().upper()
                if (
                    not question_key
                    or not reference.startswith(
                        "hunter-secure://candidate-truth/"
                    )
                    or sensitivity not in {"PROTECTED", "SELF_ID"}
                    or answer.get("autofill_allowed") is not True
                    or answer.get("execution_value") is not None
                ):
                    raise PermissionError(
                        "Protected browser answer is outside immutable plan authority"
                    )
                resolved = bridge.protected_application_value(
                    current,
                    question_key=question_key,
                    secure_resolver_ref=reference,
                )
                if (
                    str(resolved.get("question_key") or "") != question_key
                    or str(resolved.get("sensitivity") or "").upper()
                    != sensitivity
                    or str(resolved.get("provenance") or "")
                    != "candidate_truth_protected_domain"
                ):
                    raise RuntimeError(
                        "Protected browser answer response binding mismatch"
                    )
                return resolved

            def legal_attestation_authorizer(
                current: dict[str, Any],
                attestation_identity: dict[str, Any],
            ) -> dict[str, Any]:
                if str(current.get("plan_id")) != str(plan["plan_id"]) or str(
                    current.get("plan_digest")
                ) != str(plan["plan_digest"]):
                    raise ValueError(
                        "Legal attestation request no longer matches accepted plan"
                    )
                if bridge.plan_is_current(current) is not True:
                    raise ValueError(
                        "Legal attestation request belongs to a stale plan"
                    )
                proof = bridge.authorize_legal_attestation(
                    current,
                    attestation_identity=dict(attestation_identity),
                )
                if (
                    proof.get("authorized") is not True
                    or proof.get("submission_authority") is not False
                    or dict(proof.get("attestation_identity") or {})
                    != dict(attestation_identity)
                ):
                    raise RuntimeError(
                        "Legal attestation authorization response binding mismatch"
                    )
                return proof

            return HostedPlanBrowserAdapter(
                page,
                artifact_reader=artifact_reader,
                cover_letter_reader=(cover_letter_reader if cover_binding is not None else None),
                protected_value_resolver=protected_value_resolver,
                legal_attestation_authorizer=legal_attestation_authorizer,
                current_plan=current_plan,
                runtime_path=_runtime_path(),
                interaction_fallback_service=interaction_fallback,
                teach_munshi_service=self.teach_munshi_service,
                playwright_instance=pw,
                browser=browser,
                context=context,
                bridge=bridge,
            )
        except Exception:
            if context is not None:
                with suppress(Exception):
                    context.close()
            if browser is not None:
                with suppress(Exception):
                    browser.close()
            if pw is not None:
                with suppress(Exception):
                    pw.stop()
            with suppress(Exception):
                bridge.close()
            raise


class HostedPreparationRunner:
    def __init__(
        self,
        queue: DurablePreparationQueue,
        *,
        service_factory: Any,
        adapter_factory: Any,
        lease_seconds: int = 300,
        heartbeat_interval: float | None = None,
    ) -> None:
        self.queue = queue
        self.service_factory = service_factory
        self.adapter_factory = adapter_factory
        self.lease_seconds = int(lease_seconds)
        self.heartbeat_interval = (
            float(heartbeat_interval)
            if heartbeat_interval is not None
            else max(1.0, self.lease_seconds / 3)
        )

    def run_once(self, *, worker_id: str) -> PreparationRunResult | None:
        job = self.queue.claim_next(worker_id=worker_id, lease_seconds=self.lease_seconds)
        if job is None:
            return None
        stop = threading.Event()
        heartbeat_errors: list[Exception] = []

        def heartbeat_loop() -> None:
            while not stop.wait(self.heartbeat_interval):
                try:
                    self.queue.heartbeat(
                        job_id=str(job["job_id"]),
                        worker_id=worker_id,
                        lease_seconds=self.lease_seconds,
                    )
                except Exception as error:
                    heartbeat_errors.append(error)
                    return

        heartbeat = threading.Thread(
            target=heartbeat_loop, name=f"munshi-prepare-heartbeat-{job['job_id']}", daemon=True
        )
        heartbeat.start()
        adapter = None
        try:
            service = self.service_factory(job)
            service.preflight_prepare_session(str(job["session_id"]))
            queued = self.queue.get(
                job_id=str(job["job_id"]),
                tenant_id=str(job["tenant_id"]),
                user_id=str(job["user_id"]),
            )
            if queued.get("cancel_requested_at") is not None:
                raise ValueError("Hosted preparation job was cancelled")
            adapter = self.adapter_factory(job)
            result = service.prepare_session(session_id=str(job["session_id"]), adapter=adapter)
            if heartbeat_errors:
                raise RuntimeError("Hosted preparation worker lost its heartbeat lease")
            finished = self.queue.finish(
                job_id=str(job["job_id"]), worker_id=worker_id, session_state=str(result.state)
            )
            return PreparationRunResult(
                job_id=str(finished["job_id"]),
                session_id=str(finished["session_id"]),
                job_state=str(finished["state"]),
                session_state=str(result.state),
                attempt_count=int(finished["attempt_count"]),
                retry_scheduled=False,
            )
        except (LookupError, PermissionError, RuntimeError, ValueError) as error:
            failed = self.queue.fail(
                job_id=str(job["job_id"]), worker_id=worker_id, error=error, retryable=False
            )
            return PreparationRunResult(
                job_id=str(failed["job_id"]),
                session_id=str(failed["session_id"]),
                job_state=str(failed["state"]),
                session_state=None,
                attempt_count=int(failed["attempt_count"]),
                retry_scheduled=False,
            )
        except Exception as error:
            failed = self.queue.fail(
                job_id=str(job["job_id"]), worker_id=worker_id, error=error, retryable=True
            )
            return PreparationRunResult(
                job_id=str(failed["job_id"]),
                session_id=str(failed["session_id"]),
                job_state=str(failed["state"]),
                session_state=None,
                attempt_count=int(failed["attempt_count"]),
                retry_scheduled=str(failed["state"]) == "QUEUED",
            )
        finally:
            stop.set()
            heartbeat.join(timeout=max(1.0, self.heartbeat_interval * 2))
            if adapter is not None:
                close = getattr(adapter, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()


def run_forever() -> None:
    if not _truthy(BACKGROUND_PREPARE_ENV):
        raise RuntimeError("Apply background preparation is disabled")
    if not _truthy(HOSTED_WORKER_ENV):
        raise RuntimeError("Hosted Apply preparation worker is disabled")
    settings = Settings.from_environment()
    if not settings.handoff_hmac_secret:
        raise RuntimeError("Apply handoff HMAC secret is required for hosted preparation")
    bridge_url = str(os.getenv(BRIDGE_URL_ENV) or "").strip()
    if not bridge_url:
        raise RuntimeError("Hunter execution bridge base URL is required")
    if not _truthy(RESUME_UPLOAD_ENV) or not _truthy(NORMAL_AUTOFILL_ENV):
        raise RuntimeError("Hosted resume upload and normal answer autofill are disabled")
    database = Database(settings.database_path, settings.migrations_path)
    database.migrate()
    queue = DurablePreparationQueue(database)
    adapter_factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url=bridge_url,
        bridge_secret=settings.handoff_hmac_secret,
        browser_executable=os.getenv("MUNSHI_BROWSER_EXECUTABLE") or None,
        navigation_timeout_ms=int(os.getenv("MUNSHI_APPLY_BROWSER_TIMEOUT_MS", "30000")),
        runtime_root=settings.runtime_root,
    )
    runner = HostedPreparationRunner(
        queue,
        service_factory=lambda job: CompleteApplicationLoopService(
            database, tenant_id=str(job["tenant_id"]), user_id=str(job["user_id"])
        ),
        adapter_factory=adapter_factory,
        lease_seconds=int(os.getenv("MUNSHI_APPLY_PREPARE_LEASE_SECONDS", "300")),
    )
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
