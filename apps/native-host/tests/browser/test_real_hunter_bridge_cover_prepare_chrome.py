from __future__ import annotations

import hashlib
import importlib.util
import os
import secrets
import socket
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService
from munshi_apply_native.hosted_prepare_worker import HostedAdapterFactory, HostedPreparationRunner


pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_REAL_HUNTER_BRIDGE_TEST") != "1",
    reason="real cross-repository Chromium acceptance lane is opt-in",
)

RESUME = b"%PDF-1.4\n% synthetic resume\n%%EOF\n"
COVER = b"%PDF-1.4\n% synthetic cover letter\n%%EOF\n"
JOB_URL = "https://boards.greenhouse.io/synthetic/jobs/41"


def _helpers():
    path = Path(__file__).resolve().parents[1] / "test_application_plan_handoff_v2.py"
    spec = importlib.util.spec_from_file_location("real_bridge_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _helpers()


def _hunter_modules(monkeypatch: pytest.MonkeyPatch):
    root = Path(os.environ["MUNSHI_HUNTER_REPO"]).resolve()
    if not (root / "app" / "api.py").is_file():
        pytest.fail("MUNSHI_HUNTER_REPO must name a Hunter checkout")
    monkeypatch.syspath_prepend(str(root))
    from app import api, application_artifact_transport_v2 as bridge

    return api, bridge


@contextmanager
def _hunter_server(api):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_real_signed_hunter_bridge_uploads_bound_resume_and_cover_before_input(tmp_path, monkeypatch):
    monkeypatch.setenv("HUNTER_API_SECRET", secrets.token_urlsafe(32))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "hunter.sqlite"))
    monkeypatch.setenv("AADIL_HR_HUNTER_RUNTIME", str(tmp_path / "hunter-runtime"))
    api, bridge = _hunter_modules(monkeypatch)
    secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("MUNSHI_APPLY_HANDOFF_HMAC_SECRET", secret)
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    resume = {"engine": "NATIVE_V5", "version_id": "synthetic-resume", "artifact_id": "synthetic-resume", "artifact_reference": "hunter-native-resume://synthetic/pdf", "artifact_sha256": hashlib.sha256(RESUME).hexdigest(), "filename": "resume.pdf", "mime_type": "application/pdf"}
    cover = {"version": "munshi-cover-letter-artifact-v1", "artifact_id": "synthetic-cover", "artifact_reference": "hunter-cover-letter://synthetic/pdf", "artifact_sha256": hashlib.sha256(COVER).hexdigest(), "filename": "cover-letter.pdf", "mime_type": "application/pdf", "submission_authority": False}
    job = dict(H._plan()["job"])
    job.update(job_url=JOB_URL, apply_url=JOB_URL)
    plan = H._plan(resume=resume, cover_letter=cover, job=job)
    hunter_plan = {"tenant_id": "tenant-a", "user_id": "member-a", "application_id": "application-1", "plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"], "snapshot": {"owner_binding": {"tenant_id": "tenant-a", "user_id": "member-a"}, "resume": resume, "cover_letter": cover, "submission_authority": False}}
    monkeypatch.setattr(bridge.application_plan_v2, "executable_plan", lambda _id: hunter_plan)
    monkeypatch.setattr(bridge.native_resume_artifact_v5, "artifact_bytes", lambda _id: RESUME)
    monkeypatch.setattr(bridge.cover_letter_artifact_v1, "artifact_bytes", lambda _id: COVER)
    consumer, db = H._consumer(tmp_path)
    now = int(time.time())
    body, headers = H._signed(H._envelope(plan=plan), timestamp=now)
    assert consumer.accept(body, headers, now=now).accepted
    service = CompleteApplicationLoopService(db, tenant_id="tenant-a", user_id="member-a")
    session = service.start_session(plan_id=str(plan["plan_id"]))
    queue = DurablePreparationQueue(db)
    queue.enqueue_session(session_id=session.session_id, tenant_id="tenant-a", user_id="member-a")
    allowed, denied = [], []
    html = """<form method='post'><label for='first_name'>First name</label><input id='first_name' required><label for='resume'>Resume</label><input id='resume' type='file' required><label for='cover_letter'>Cover Letter</label><input id='cover_letter' type='file' required><button>Submit application</button></form>"""

    def configure(context, _plan):
        def route(handler):
            request = handler.request
            if request.url == JOB_URL and request.method == "GET":
                allowed.append((request.method, request.url))
                handler.fulfill(status=200, content_type="text/html", body=html)
            else:
                denied.append((request.method, request.url))
                handler.abort()
        context.route("**/*", route)

    with _hunter_server(api) as base_url:
        factory = HostedAdapterFactory(db, queue, bridge_base_url=base_url, bridge_secret=secret, context_configurer=configure)
        result = HostedPreparationRunner(queue, service_factory=lambda _job: service, adapter_factory=factory, lease_seconds=30, heartbeat_interval=0.05).run_once(worker_id="synthetic-worker")
    assert result is not None and result.job_state == "WAITING_INPUT" and result.session_state == "NEEDS_INPUT", queue.get(job_id=result.job_id, tenant_id="tenant-a", user_id="member-a")["last_error"]
    assert allowed == [("GET", JOB_URL)] and not denied
    with db.connect() as connection:
        evidence = connection.execute("SELECT evidence_json FROM complete_application_execution_events WHERE session_id=? AND event_type='FORM_PREPARED'", (session.session_id,)).fetchone()
        assert evidence is not None and resume["artifact_sha256"] in evidence["evidence_json"] and cover["artifact_sha256"] in evidence["evidence_json"]
        for table in ("final_application_reviews", "final_submit_commands", "application_submission_receipts", "application_mail_events"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
