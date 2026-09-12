#!/usr/bin/env python3
"""Side-effect-free proof worker for the MUNSHI <-> autonomous-worker contract.

This intentionally does not import ApplyPilot or launch a browser. It proves the
quarantine boundary and fails closed before the real adapter is introduced.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_ENVIRONMENTS = {"local-test", "ci"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fail(message: str) -> None:
    raise ValueError(message)


def validate_request(payload: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "plan_id",
        "plan_digest",
        "job",
        "artifacts",
        "answers",
        "permissions",
        "execution_context",
    }
    missing = sorted(required - payload.keys())
    if missing:
        fail(f"missing required fields: {', '.join(missing)}")

    if payload.get("schema_version") != "1.0":
        fail("unsupported schema_version")

    context = payload["execution_context"]
    if not isinstance(context, dict):
        fail("execution_context must be an object")
    if context.get("synthetic") is not True:
        fail("mock worker only accepts synthetic=true")
    if context.get("environment") not in ALLOWED_ENVIRONMENTS:
        fail("mock worker only accepts local-test or ci")

    permissions = payload["permissions"]
    if not isinstance(permissions, dict):
        fail("permissions must be an object")
    if permissions.get("security_checkpoint_bypass") is not False:
        fail("security_checkpoint_bypass must remain false")
    if permissions.get("final_submit") is True:
        fail("mock worker refuses final_submit=true")

    answers = payload["answers"]
    if not isinstance(answers, list):
        fail("answers must be an array")
    for answer in answers:
        if not isinstance(answer, dict) or answer.get("approved") is not True:
            fail("every supplied answer must be explicitly approved")


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    run_id = f"mock-{uuid.uuid4()}"

    events = [
        {
            "sequence": 1,
            "kind": "WORKER_REQUEST_ACCEPTED",
            "timestamp": utc_now(),
            "verified": True,
            "control_id": None,
            "question_key": None,
            "artifact_sha256": None,
            "detail": "Synthetic request accepted by quarantined mock worker.",
        },
        {
            "sequence": 2,
            "kind": "SYNTHETIC_EXECUTION_COMPLETE",
            "timestamp": utc_now(),
            "verified": True,
            "control_id": None,
            "question_key": None,
            "artifact_sha256": None,
            "detail": "No browser launched and no external side effect performed.",
        },
    ]

    elapsed = max(0.0, time.monotonic() - started)
    return {
        "schema_version": "1.0",
        "worker_run_id": run_id,
        "plan_id": payload["plan_id"],
        "plan_digest": payload["plan_digest"],
        "status": "COMPLETED",
        "final_url": payload["job"]["url"],
        "provider": payload["job"].get("provider"),
        "provider_application_id": None,
        "claimed_submission": False,
        "needs_input": [],
        "events": events,
        "submission_observation": None,
        "cost": {
            "estimated_total_usd": 0.0,
            "agent_usd": 0.0,
            "captcha_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "agent_steps": 0,
            "wall_seconds": elapsed,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the side-effect-free autonomous worker mock")
    parser.add_argument("request", type=Path, help="Path to a request JSON document")
    parser.add_argument("--output", type=Path, help="Optional result JSON path")
    args = parser.parse_args()

    try:
        payload = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("request document must contain a JSON object")
        validate_request(payload)
        result = execute(payload)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        print(f"mock worker rejected request: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
