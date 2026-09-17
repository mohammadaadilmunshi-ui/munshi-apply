from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BRIDGE = Path(__file__).resolve().parents[3] / "integrations" / "applypilot" / "bridge"
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

worker = importlib.import_module("autonomous_worker")


def test_legacy_autonomous_worker_cannot_bypass_canonical_executor(
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
        "_run_agent",
        lambda **_kwargs: (
            {"status": "COMPLETED", "claimed_submission": False, "reason": "prepared"},
            {},
        ),
    )
    claimed = []
    monkeypatch.setattr(
        worker,
        "claim_submit_authorization",
        lambda *_args, **_kwargs: claimed.append(True),
    )

    with pytest.raises(worker.WorkerError, match="canonical Complete Application Loop"):
        worker.execute(request_path, dry_run=False, port=9222)
    assert claimed == []
