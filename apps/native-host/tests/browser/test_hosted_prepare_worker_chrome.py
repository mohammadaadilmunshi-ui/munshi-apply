from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pytest

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService
from munshi_apply_native.hosted_prepare_worker import (
    HostedAdapterFactory,
    HostedPreparationRunner,
)

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

RESUME_BYTES = (
    b"%PDF-1.4\n"
    b"% MUNSHI hosted-worker fixture only\n"
    b"1 0 obj <<>> endobj\n"
    b"trailer <<>>\n"
    b"%%EOF\n"
)
RESUME_SHA = hashlib.sha256(RESUME_BYTES).hexdigest()
JOB_URL = "https://boards.greenhouse.io/example/jobs/41"


def _load_handoff_helpers() -> ModuleType:
    helpers_path = (
        Path(__file__).resolve().parents[1]
        / "test_application_plan_handoff_v2.py"
    )
    spec = importlib.util.spec_from_file_location(
        "munshi_test_application_plan_handoff_v2",
        helpers_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Could not load Complete Application Loop test helpers"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HELPERS = _load_handoff_helpers()


class _Bridge:
    def __init__(self, **_kwargs: object) -> None:
        self.closed = False

    def artifact_bytes(self, _plan: dict[str, object]) -> bytes:
        return RESUME_BYTES

    def plan_is_current(self, _plan: dict[str, object]) -> bool:
        return True

    def close(self) -> None:
        self.closed = True


def test_hosted_runner_uses_real_chromium_and_stops_at_needs_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")

    resume = {
        "engine": "NATIVE_V5",
        "version_id": "resume-v5-1",
        "artifact_id": "resume-artifact-1",
        "artifact_reference": "hunter-native-resume://resume-v5-1/pdf",
        "artifact_sha256": RESUME_SHA,
        "filename": "fixture_resume.pdf",
        "mime_type": "application/pdf",
    }
    plan = _HELPERS._plan(resume=resume)
    consumer, database = _HELPERS._consumer(tmp_path)
    body, headers = _HELPERS._signed(_HELPERS._envelope(plan=plan))

    assert consumer.accept(body, headers, now=1000).accepted

    service = CompleteApplicationLoopService(
        database,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    session = service.start_session(plan_id=str(plan["plan_id"]))

    queue = DurablePreparationQueue(database)
    queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
    )

    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "greenhouse_like_application.html"
    )
    html = fixture.read_text(encoding="utf-8")

    def configure(context: object, _plan_value: dict[str, object]) -> None:
        def handler(route: object) -> None:
            request = route.request
            if request.url == JOB_URL and request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=html,
                )
            else:
                route.abort()

        context.route("**/*", handler)

    factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url="http://hunter.internal",
        bridge_secret="-".join(
            ("phase1cb", "browser", "fixture", "secret")
        ),
        bridge_factory=_Bridge,
        context_configurer=configure,
    )
    runner = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=factory,
        lease_seconds=30,
        heartbeat_interval=0.05,
    )

    result = runner.run_once(worker_id="browser-worker-1")

    assert result is not None
    assert result.job_state == "WAITING_INPUT"
    assert result.session_state == "NEEDS_INPUT"

    with database.connect() as connection:
        stored = connection.execute(
            "SELECT state,browser_form_digest,checkpoint_id "
            "FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()

    assert stored is not None
    assert stored["state"] == "NEEDS_INPUT"
    assert len(stored["browser_form_digest"]) == 64
    assert stored["checkpoint_id"]
