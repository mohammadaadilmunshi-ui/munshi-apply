from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

BRIDGE = Path(__file__).resolve().parents[3] / "integrations" / "applypilot" / "bridge"
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

worker = importlib.import_module("autonomous_worker")


def test_post_claim_worker_failure_is_not_reported_as_safe_retry(
    tmp_path: Path, monkeypatch
) -> None:
    request = {
        "permissions": {"final_submit": True},
        "execution_context": {"synthetic": False},
        "budget": {},
        "job": {"url": "https://jobs.example.test/apply", "provider": "TEST"},
        "plan_id": "plan-1",
        "plan_digest": "a" * 64,
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    monkeypatch.setattr(worker, "_validate_request", lambda _request: None)
    monkeypatch.setattr(
        worker,
        "_load_settings",
        lambda: worker.WorkerSettings(allow_final_submit=True),
    )
    monkeypatch.setattr(worker.shutil, "which", lambda _name: "/bin/true")
    monkeypatch.setattr(
        worker,
        "_launch_browser",
        lambda _port, _headless: worker.BrowserProcess(
            process=SimpleNamespace(), port=9222, profile_dir=tmp_path
        ),
    )
    monkeypatch.setattr(worker, "_kill_process_tree", lambda _process: None)
    monkeypatch.setattr(
        worker,
        "_validate_authorization_binding",
        lambda _request: {
            "authorization_id": "auth-1",
            "authority_digest": "b" * 64,
            "target_url": "https://jobs.example.test/submit",
        },
    )
    monkeypatch.setattr(
        worker,
        "claim_submit_authorization",
        lambda _auth, claimant_id: {
            "authorization_id": "auth-1",
            "authority_digest": "b" * 64,
            "claim_digest": "c" * 64,
            "generation": 1,
            "status": "CLAIMED",
            "submission_authority": True,
        },
    )

    calls = 0

    def run_agent(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return (
                {
                    "status": "COMPLETED",
                    "claimed_submission": False,
                    "reason": "prepared",
                },
                {},
            )
        raise worker.WorkerError("agent connection lost")

    monkeypatch.setattr(worker, "_run_agent", run_agent)

    result = worker.execute(request_path, dry_run=False, port=9222)

    assert result["status"] == "BLOCKED"
    assert result["claimed_submission"] is False
    assert result["submission_outcome"] == "UNKNOWN_AFTER_AUTHORITY_CLAIM"
    assert result["submit_authorization_claim"]["status"] == "CLAIMED"
    assert "reconciliation" in result["events"][-1]["detail"].lower()
