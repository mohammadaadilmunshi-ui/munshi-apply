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
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1",
    reason="real browser integration lane is opt-in",
)

RESUME_BYTES = (
    b"%PDF-1.4\n"
    b"% MUNSHI runtime supersession fixture\n"
    b"1 0 obj <<>> endobj\n"
    b"trailer <<>>\n"
    b"%%EOF\n"
)
RESUME_SHA = hashlib.sha256(RESUME_BYTES).hexdigest()
JOB_URL = "https://boards.greenhouse.io/example/jobs/41"


def _helpers():
    path = Path(__file__).resolve().parents[1] / "test_application_plan_handoff_v2.py"
    spec = importlib.util.spec_from_file_location(
        "runtime_supersession_browser_helpers", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _helpers()


class _Bridge:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def artifact_bytes(self, _plan: dict[str, object]) -> bytes:
        return RESUME_BYTES

    def plan_is_current(self, _plan: dict[str, object]) -> bool:
        return True

    def close(self) -> None:
        pass


def test_runtime_supersession_requeues_same_session_and_reaches_ready_for_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    resume = {
        "engine": "NATIVE_V5",
        "version_id": "resume-v5-1",
        "artifact_id": "resume-artifact-1",
        "artifact_reference": "hunter-native-resume://resume-v5-1/pdf",
        "artifact_sha256": RESUME_SHA,
        "filename": "fixture_resume.pdf",
        "mime_type": "application/pdf",
    }
    prior = H._plan(resume=resume)
    consumer, database = H._consumer(tmp_path)
    body, headers = H._signed(H._envelope(plan=prior))
    assert consumer.accept(body, headers, now=1000).accepted
    service = CompleteApplicationLoopService(
        database, tenant_id="tenant-a", user_id="member-a"
    )
    session = service.start_session(plan_id=str(prior["plan_id"]))
    queue = DurablePreparationQueue(database)
    job = queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    html = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "greenhouse_like_application.html"
    ).read_text(encoding="utf-8")

    def configure(context: object, _plan_value: dict[str, object]) -> None:
        def handler(route: object) -> None:
            request = route.request
            if request.url == JOB_URL and request.method == "GET":
                route.fulfill(status=200, content_type="text/html", body=html)
            else:
                route.abort()
        context.route("**/*", handler)

    factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url="http://hunter.internal",
        bridge_secret="-".join(("runtime", "supersession", "browser", "secret")),
        bridge_factory=_Bridge,
        context_configurer=configure,
    )
    first = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=factory,
        lease_seconds=30,
        heartbeat_interval=0.05,
    ).run_once(worker_id="browser-runtime-1")
    assert first is not None
    assert first.job_state == "WAITING_INPUT"
    assert first.session_state == "NEEDS_INPUT"
    with database.connect() as connection:
        stored_session = connection.execute(
            """SELECT checkpoint_id,browser_form_digest FROM complete_application_sessions
               WHERE session_id=?""",
            (session.session_id,),
        ).fetchone()
        task_rows = connection.execute(
            """SELECT task_id,control_id,question,semantic_type,group_key
               FROM resolution_tasks
               WHERE session_id=? AND status='WAITING_FOR_USER'
               ORDER BY group_key""",
            (session.session_id,),
        ).fetchall()
    assert stored_session is not None
    assert task_rows
    replacement = H._plan(
        plan_id="application-plan-runtime-2",
        idempotency_key="plan-runtime-key-2",
        resume=resume,
        answers=[
            {
                "question_key": str(row["group_key"]),
                "normalized_question": str(row["question"]),
                "sensitivity_class": "NORMAL",
                "execution_value": (
                    "Aadil" if "first" in str(row["group_key"]).casefold() else "Munshi"
                ),
                "autofill_allowed": True,
            }
            for row in task_rows
        ],
    )
    supersession = {
        "version": "munshi-application-plan-supersession-v1",
        "prior_plan_id": str(prior["plan_id"]),
        "prior_plan_digest": str(prior["plan_digest"]),
        "replacement_plan_id": str(replacement["plan_id"]),
        "replacement_plan_digest": str(replacement["plan_digest"]),
        "resolution_digest": "e" * 64,
        "session_id": session.session_id,
        "checkpoint_id": str(stored_session["checkpoint_id"]),
        "browser_form_digest": str(stored_session["browser_form_digest"]),
        "unresolved_questions": [
            {
                "question_key": str(row["group_key"]),
                "control_id": str(row["control_id"]),
                "question": str(row["question"]),
                "semantic_type": str(row["semantic_type"]),
                "sensitivity_class": "NORMAL",
            }
            for row in task_rows
        ],
    }
    envelope = H._envelope(
        plan=replacement,
        handoff_id="plan-handoff-runtime-2",
        version="munshi-application-plan-handoff-v3",
        content_contract={
            "application_plan_version": "munshi-application-plan-v2",
            "receiver_min_version": 3,
            "receiver_max_version": 3,
        },
        supersession=supersession,
    )
    body, headers = H._signed(envelope, timestamp=1001)
    accepted = consumer.accept(body, headers, now=1001)
    assert accepted.accepted and not accepted.replayed
    assert accepted.resumed_session_id == session.session_id
    assert accepted.preparation_job_id == job["job_id"]

    second_factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url="http://hunter.internal",
        bridge_secret="-".join(("runtime", "supersession", "browser", "secret")),
        bridge_factory=_Bridge,
        context_configurer=configure,
    )
    second = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=second_factory,
        lease_seconds=30,
        heartbeat_interval=0.05,
    ).run_once(worker_id="browser-runtime-2")
    assert second is not None
    assert second.job_state == "READY_FOR_REVIEW"
    assert second.session_state == "READY_FOR_REVIEW"
    assert second.session_id == session.session_id
    with database.connect() as connection:
        current = connection.execute(
            "SELECT plan_id,state FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
        prepare = connection.execute(
            "SELECT plan_id,state FROM complete_application_prepare_jobs WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()
        expired = connection.execute(
            "SELECT COUNT(*) FROM resolution_tasks WHERE session_id=? AND status='EXPIRED'",
            (session.session_id,),
        ).fetchone()[0]
        zero_side_effect_queries = (
            "SELECT COUNT(*) FROM final_application_reviews",
            "SELECT COUNT(*) FROM final_submit_commands",
            "SELECT COUNT(*) FROM application_submission_receipts",
            "SELECT COUNT(*) FROM application_mail_events",
        )
        for query in zero_side_effect_queries:
            assert connection.execute(query).fetchone()[0] == 0
    assert current["plan_id"] == replacement["plan_id"]
    assert current["state"] == "READY_FOR_REVIEW"
    assert prepare["plan_id"] == replacement["plan_id"]
    assert prepare["state"] == "READY_FOR_REVIEW"
    assert expired == len(task_rows)
