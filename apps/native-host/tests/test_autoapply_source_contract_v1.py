from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


ROOT = Path(__file__).resolve().parents[3]

CANONICAL_RUNTIME_FILES = (
    ROOT / "apps/native-host/src/munshi_apply_native/plan_browser_adapter.py",
    ROOT / "apps/native-host/src/munshi_apply_native/hosted_prepare_worker.py",
    ROOT / "apps/native-host/src/munshi_apply_native/hosted_submit_worker.py",
    ROOT / "apps/native-host/src/munshi_apply_native/complete_application_loop.py",
    ROOT / "apps/native-host/src/munshi_apply_native/hosted_account_orchestrator.py",
)

FORBIDDEN_ACCEPTANCE_LITERALS = (
    "MUNSHI_NEOMAX",
    "neomax.jobs",
)


def test_canonical_apply_runtime_has_no_acceptance_job_literals() -> None:
    violations: list[str] = []
    for path in CANONICAL_RUNTIME_FILES:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for literal in FORBIDDEN_ACCEPTANCE_LITERALS:
            if literal in content:
                violations.append(f"{path.relative_to(ROOT)}:{literal}")
    assert violations == []


def test_plan_bound_upload_proof_survives_only_current_session_rerender(monkeypatch) -> None:
    plan = {
        "plan_id": "plan-1",
        "job": {
            "id": "job-1",
            "job_url": "https://jobs.example.test/job-1",
            "apply_url": "https://jobs.example.test/job-1",
        },
        "provider_policy": {
            "provider": "GENERIC",
            "allowed_hosts": ["jobs.example.test"],
        },
        "resume": {
            "artifact_sha256": "a" * 64,
        },
    }
    current = {"value": True}
    adapter = PlanBrowserAdapter(
        SimpleNamespace(url="https://jobs.example.test/job-1"),
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: current["value"],
        runtime_path=ROOT / "apps/native-host/browser-dist/plan-runtime.js",
    )
    adapter._remember_verified_upload(
        plan=plan,
        role="resume",
        expected_sha256="a" * 64,
    )

    assert adapter._remembered_upload(plan=plan, role="resume") == "a" * 64
    current["value"] = False
    assert adapter._remembered_upload(plan=plan, role="resume") == ""


def test_observe_uses_plan_bound_verified_upload_after_spa_element_replacement(
    monkeypatch,
) -> None:
    plan = {
        "plan_id": "plan-2",
        "job": {
            "id": "job-2",
            "job_url": "https://jobs.example.test/job-2",
            "apply_url": "https://jobs.example.test/job-2",
        },
        "provider_policy": {
            "provider": "GENERIC",
            "allowed_hosts": ["jobs.example.test"],
        },
        "resume": {
            "artifact_sha256": "b" * 64,
        },
    }
    adapter = PlanBrowserAdapter(
        SimpleNamespace(url="https://jobs.example.test/job-2"),
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=ROOT / "apps/native-host/browser-dist/plan-runtime.js",
    )
    adapter._remember_verified_upload(
        plan=plan,
        role="resume",
        expected_sha256="b" * 64,
    )
    monkeypatch.setattr(
        adapter,
        "_scan",
        lambda: {
            "page": {
                "controls": [
                    {
                        "controlId": "replacement-file-control",
                        "inputType": "file",
                    }
                ],
                "navigationCandidates": [],
            },
            "fields": [],
        },
    )
    monkeypatch.setattr(adapter, "_file_sha256", lambda _control_id: "")
    monkeypatch.setattr(
        adapter,
        "inspect_job",
        lambda plan: {
            "provider": "GENERIC",
            "provider_recipe": "GENERIC",
            "job_id": "job-2",
            "current_url": "https://jobs.example.test/job-2",
            "page_id": "page-2",
            "page_fingerprint": "fingerprint",
            "security_checkpoint": None,
        },
    )
    monkeypatch.setattr(adapter, "_submit_binding", lambda: None)

    observed = adapter._observe(plan)

    assert observed["resume_uploaded"] is True
    assert observed["resume_sha256"] == "b" * 64


def test_production_enables_runtime_plan_supersession() -> None:
    compose = (ROOT / "deploy/production/compose.yaml").read_text(encoding="utf-8")
    assert "MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED" in compose
    assert "${MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED:-true}" in compose
