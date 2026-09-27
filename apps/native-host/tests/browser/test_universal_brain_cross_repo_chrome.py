from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.complete_application_loop import CompleteApplicationLoopService
from munshi_apply_native.hosted_prepare_worker import HostedAdapterFactory, HostedPreparationRunner

pytestmark = pytest.mark.skipif(
    os.getenv("MUNSHI_RUN_BROWSER_TESTS") != "1"
    or os.getenv("MUNSHI_RUN_UNIVERSAL_CROSS_REPO_TEST") != "1",
    reason="Universal Brain cross-repository Chromium acceptance lane is opt-in",
)

RESUME_BYTES = b"%PDF-1.4\n% universal brain synthetic resume\n%%EOF\n"
RESUME_SHA = hashlib.sha256(RESUME_BYTES).hexdigest()
JOB_URL = "https://boards.greenhouse.io/example/jobs/41"
TEST_BRIDGE_SECRET = "universal-cross-repo-browser-secret"


def _helpers():
    path = Path(__file__).resolve().parents[1] / "test_application_plan_handoff_v2.py"
    spec = importlib.util.spec_from_file_location("universal_cross_repo_helpers", path)
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


def _hunter_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = Path(os.environ["MUNSHI_HUNTER_REPO"]).resolve()
    assert (root / "app" / "candidate_knowledge_graph_v1.py").is_file()
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "hunter-universal.sqlite"))
    monkeypatch.setenv("AADIL_HR_HUNTER_RUNTIME", str(tmp_path / "hunter-runtime"))
    monkeypatch.setenv("AADIL_HR_HUNTER_LOGS", str(tmp_path / "hunter-logs"))
    monkeypatch.setenv("MUNSHI_UNIVERSAL_BRAIN_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_UNIVERSAL_ONTOLOGY_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_UNIVERSAL_EMBEDDING_ENABLED", "true")
    monkeypatch.syspath_prepend(str(root))
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]
    from app import application_semantic_binding_v1 as hunter_binding
    from app import candidate_knowledge_graph_v1 as hunter_graph
    from app import universal_answer_resolver_v1 as hunter_answers
    from app import universal_semantic_embedding_v1 as hunter_embedding

    return hunter_binding, hunter_graph, hunter_answers, hunter_embedding


def _html(control_id: str) -> str:
    return f"""<!doctype html>
<html><body>
<main>
  <h1>People Analytics Specialist</h1>
  <form id="application-form" method="post">
    <label for="resume">Resume</label>
    <input id="resume" name="resume" type="file" accept=".pdf,application/pdf" required />
    <section aria-label="Personal details">
      <label for="{control_id}">Primary domicile jurisdiction</label>
      <select id="{control_id}" name="home_jurisdiction" role="combobox" required>
        <option value="">Choose one</option>
        <option>New Jersey</option>
        <option>New York</option>
        <option>Pennsylvania</option>
        <option>Delaware</option>
      </select>
    </section>
    <button id="submit-app" type="submit">Submit application</button>
  </form>
</main>
</body></html>"""


def test_candidate_knowledge_to_weird_wording_to_supersession_to_verified_browser_fill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hunter_binding, hunter_graph, hunter_answers, hunter_embedding = _hunter_modules(
        tmp_path, monkeypatch
    )

    stored = hunter_graph.store_fact(
        concept_id="contact.region",
        value="New Jersey",
        value_type="string",
        source_type="USER_DASHBOARD",
        source_ref="synthetic-dashboard:contact.region",
        trust_level="USER_CONFIRMED",
        confidence=1.0,
        sensitivity="NORMAL",
        autofill_policy="ALLOW",
    )
    assert stored["concept_id"] == "contact.region"

    # Force the acceptance case through the standalone embedding lane while
    # preserving the exact production resolver/answer/binding contracts.
    monkeypatch.setattr(
        hunter_embedding,
        "retrieve_fail_closed",
        lambda observation, top_k=8: [
            {
                "concept_id": "contact.region",
                "score": 0.95,
                "sensitivity": "NORMAL",
                "answer_mode": "DIRECT_FACT",
                "category": "CONTACT",
                "description": "Candidate state or province of residence.",
            },
            {
                "concept_id": "contact.city",
                "score": 0.72,
                "sensitivity": "NORMAL",
                "answer_mode": "DIRECT_FACT",
                "category": "CONTACT",
                "description": "Candidate city of residence.",
            },
        ],
    )

    monkeypatch.setenv("MUNSHI_APPLY_LIVE_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_BACKGROUND_PREPARE_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_RESUME_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")

    resume = {
        "engine": "NATIVE_V5",
        "version_id": "resume-v5-universal-cross-repo",
        "artifact_id": "resume-artifact-universal-cross-repo",
        "artifact_reference": "hunter-native-resume://universal-cross-repo/pdf",
        "artifact_sha256": RESUME_SHA,
        "filename": "fixture_resume.pdf",
        "mime_type": "application/pdf",
    }
    prior = H._plan(
        plan_id="application-plan-universal-cross-repo-1",
        idempotency_key="plan-universal-cross-repo-key-1",
        resume=resume,
    )
    consumer, database = H._consumer(tmp_path)
    body, headers = H._signed(
        H._envelope(plan=prior, handoff_id="plan-handoff-universal-cross-repo-1")
    )
    assert consumer.accept(body, headers, now=1200).accepted

    service = CompleteApplicationLoopService(
        database, tenant_id="tenant-a", user_id="member-a"
    )
    session = service.start_session(plan_id=str(prior["plan_id"]))
    queue = DurablePreparationQueue(database)
    queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
    )
    active_html = {"value": _html("domicile-v1")}

    def configure(context: object, _plan_value: dict[str, object]) -> None:
        def handler(route: object) -> None:
            request = route.request
            if request.url == JOB_URL and request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=active_html["value"],
                )
            else:
                route.abort()

        context.route("**/*", handler)

    factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url="http://hunter.internal",
        bridge_secret=TEST_BRIDGE_SECRET,
        bridge_factory=_Bridge,
        context_configurer=configure,
    )
    first = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=factory,
        lease_seconds=30,
        heartbeat_interval=0.05,
    ).run_once(worker_id="browser-universal-cross-repo-1")
    assert first is not None
    assert first.job_state == "WAITING_INPUT"
    assert first.session_state == "NEEDS_INPUT"

    with database.connect() as connection:
        stored_session = connection.execute(
            """SELECT checkpoint_id,browser_form_digest
               FROM complete_application_sessions WHERE session_id=?""",
            (session.session_id,),
        ).fetchone()
        task_rows = connection.execute(
            """SELECT task_id,control_id,question,semantic_type,group_key,
                      question_observation_json
               FROM resolution_tasks
               WHERE session_id=? AND status='WAITING_FOR_USER'""",
            (session.session_id,),
        ).fetchall()
    assert stored_session is not None
    assert len(task_rows) == 1
    task = task_rows[0]
    observation = json.loads(str(task["question_observation_json"]))
    assert "domicile" in str(task["question"]).casefold()

    knowledge_view = {
        "profile_revision": 1,
        "facts": hunter_graph.current_facts(),
        "answer_memory": [],
        "claims": [],
        "profile": {},
    }
    resolution = hunter_answers.resolve_observation(
        observation,
        knowledge_view=knowledge_view,
    )
    assert resolution["answer_status"] == "ANSWERED"
    assert resolution["concept_id"] == "contact.region"
    assert resolution["value"] == "New Jersey"
    assert resolution["autofill_allowed"] is True
    assert (
        resolution["question_resolution"]["classification_lane"]
        == "ONTOLOGY_EMBEDDING"
    )

    fingerprint = hunter_binding.fingerprint_parts(observation)[
        "logical_field_fingerprint"
    ]
    replacement = H._plan(
        plan_id="application-plan-universal-cross-repo-2",
        idempotency_key="plan-universal-cross-repo-key-2",
        resume=resume,
        answers=[
            {
                "question_key": "universal.runtime.contact.region",
                "normalized_question": "Canonical Universal Brain region",
                "universal_concept_id": "contact.region",
                "universal_value_ref": str(resolution["value_ref"]),
                "universal_binding_fingerprint": fingerprint,
                "sensitivity_class": "NORMAL",
                "execution_value": str(resolution["value"]),
                "autofill_allowed": True,
            }
        ],
    )
    supersession = {
        "version": "munshi-application-plan-supersession-v1",
        "prior_plan_id": str(prior["plan_id"]),
        "prior_plan_digest": str(prior["plan_digest"]),
        "replacement_plan_id": str(replacement["plan_id"]),
        "replacement_plan_digest": str(replacement["plan_digest"]),
        "resolution_digest": "c" * 64,
        "session_id": session.session_id,
        "checkpoint_id": str(stored_session["checkpoint_id"]),
        "browser_form_digest": str(stored_session["browser_form_digest"]),
        "unresolved_questions": [
            {
                "question_key": str(task["group_key"]),
                "control_id": str(task["control_id"]),
                "question": str(task["question"]),
                "semantic_type": str(task["semantic_type"]),
                "sensitivity_class": "NORMAL",
            }
        ],
    }
    envelope = H._envelope(
        plan=replacement,
        handoff_id="plan-handoff-universal-cross-repo-2",
        version="munshi-application-plan-handoff-v3",
        content_contract={
            "application_plan_version": "munshi-application-plan-v2",
            "receiver_min_version": 3,
            "receiver_max_version": 3,
        },
        supersession=supersession,
    )
    body, headers = H._signed(envelope, timestamp=1201)
    accepted = consumer.accept(body, headers, now=1201)
    assert accepted.accepted and not accepted.replayed
    assert accepted.resumed_session_id == session.session_id

    # SPA-style rerender changes the browser control identity after semantic
    # resolution; the logical binding must still recover the same concept/value.
    active_html["value"] = _html("domicile-v2")
    second_factory = HostedAdapterFactory(
        database,
        queue,
        bridge_base_url="http://hunter.internal",
        bridge_secret=TEST_BRIDGE_SECRET,
        bridge_factory=_Bridge,
        context_configurer=configure,
    )
    second = HostedPreparationRunner(
        queue,
        service_factory=lambda _job: service,
        adapter_factory=second_factory,
        lease_seconds=30,
        heartbeat_interval=0.05,
    ).run_once(worker_id="browser-universal-cross-repo-2")

    assert second is not None
    assert second.job_state == "READY_FOR_REVIEW"
    assert second.session_state == "READY_FOR_REVIEW"
    assert second.session_id == session.session_id

    with database.connect() as connection:
        waiting = connection.execute(
            """SELECT COUNT(*)
               FROM resolution_tasks
               WHERE session_id=? AND status='WAITING_FOR_USER'""",
            (session.session_id,),
        ).fetchone()[0]
        expired = connection.execute(
            "SELECT COUNT(*) FROM resolution_tasks WHERE session_id=? AND status='EXPIRED'",
            (session.session_id,),
        ).fetchone()[0]
        final_reviews = connection.execute(
            "SELECT COUNT(*) FROM final_application_reviews"
        ).fetchone()[0]
        submit_commands = connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0]
    assert waiting == 0
    assert expired == 1
    assert final_reviews == 0
    assert submit_commands == 0
