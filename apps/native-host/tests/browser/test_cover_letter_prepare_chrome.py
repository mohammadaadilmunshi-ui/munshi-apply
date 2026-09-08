from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path

import pytest

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService
from munshi_apply_native.hosted_prepare_worker import HostedAdapterFactory, HostedPreparationRunner

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1", reason="real browser integration lane is opt-in"
)
RESUME = b"%PDF-1.4\n% resume cover test\n%%EOF\n"
COVER = b"%PDF-1.4\n% cover test\n%%EOF\n"
RS = hashlib.sha256(RESUME).hexdigest()
CS = hashlib.sha256(COVER).hexdigest()
JOB_URL = "https://boards.greenhouse.io/example/jobs/41"


def helpers():
    path = Path(__file__).resolve().parents[1] / "test_application_plan_handoff_v2.py"
    spec = importlib.util.spec_from_file_location("munshi_cover_helpers", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = helpers()


class Bridge:
    def __init__(self, **_k):
        pass

    def artifact_bytes(self, _p):
        return RESUME

    def cover_letter_bytes(self, _p):
        return COVER

    def plan_is_current(self, _p):
        return True

    def close(self):
        pass


def test_real_chromium_resume_and_cover_before_needs_input(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")
    resume = {
        "engine": "NATIVE_V5",
        "version_id": "resume-cover-browser",
        "artifact_id": "resume-cover-browser",
        "artifact_reference": "hunter-native-resume://cover-browser/pdf",
        "artifact_sha256": RS,
        "filename": "resume.pdf",
        "mime_type": "application/pdf",
    }
    cover = {
        "version": "munshi-cover-letter-artifact-v1",
        "artifact_id": "cover-browser",
        "artifact_reference": "hunter-cover-letter://cover-browser/pdf",
        "artifact_sha256": CS,
        "filename": "cover-letter.pdf",
        "mime_type": "application/pdf",
        "submission_authority": False,
    }
    plan = H._plan(resume=resume, cover_letter=cover)
    consumer, db = H._consumer(tmp_path)
    body, headers = H._signed(H._envelope(plan=plan))
    assert consumer.accept(body, headers, now=1000).accepted
    service = CompleteApplicationLoopService(db, tenant_id="tenant-a", user_id="member-a")
    session = service.start_session(plan_id=str(plan["plan_id"]))
    q = DurablePreparationQueue(db)
    q.enqueue_session(session_id=session.session_id, tenant_id="tenant-a", user_id="member-a")
    html = """<!doctype html><html><body><form action="/applications" method="post">
    <label for="first_name">First name</label><input id="first_name" name="first_name" required>
    <label for="resume">Resume</label><input id="resume" name="resume" type="file" required>
    <label for="cover_letter">Cover Letter</label>
    <input id="cover_letter" name="cover_letter" type="file" required>
    <button type="submit">Submit application</button></form></body></html>"""

    def configure(context, _plan):
        def handler(route):
            if route.request.url == JOB_URL and route.request.method == "GET":
                route.fulfill(status=200, content_type="text/html", body=html)
            else:
                route.abort()

        context.route("**/*", handler)

    factory = HostedAdapterFactory(
        db,
        q,
        bridge_base_url="http://hunter.internal",
        bridge_secret="phase1d-browser-cover-secret",  # noqa: S106 - synthetic test-only key
        bridge_factory=Bridge,
        context_configurer=configure,
    )
    runner = HostedPreparationRunner(
        q,
        service_factory=lambda _j: service,
        adapter_factory=factory,
        lease_seconds=30,
        heartbeat_interval=0.05,
    )
    r = runner.run_once(worker_id="cover-browser-worker")
    assert r is not None and r.job_state == "WAITING_INPUT" and r.session_state == "NEEDS_INPUT"
    with db.connect() as c:
        e = c.execute(
            "SELECT evidence_json FROM complete_application_execution_events "
            "WHERE session_id=? AND event_type='FORM_PREPARED' "
            "ORDER BY occurred_at DESC LIMIT 1",
            (session.session_id,),
        ).fetchone()
    assert e is not None and RS in str(e["evidence_json"]) and CS in str(e["evidence_json"])
