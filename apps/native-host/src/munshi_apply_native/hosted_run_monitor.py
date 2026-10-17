"""Read-only live Apply status for the browser extension's hosted-run inspector.

This is an explicitly configured SSH observer, not an alternate application
executor. It reads the SAME durable Apply database used by the dashboard and
Netcup workers. No application answers, credentials or resume bytes leave it.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

_ID = re.compile(r"^application-[a-zA-Z0-9-]{8,120}$")
_HOST = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.@_-]{1,160}$")
_CONTAINER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,100}$")
_CONFIG_DEFAULT = Path.home() / ".config" / "munshi-apply" / "hosted-monitor.json"

# Runs INSIDE the fixed Apply container, using the production SQLite connection
# in query-only mode. Sensitive question answers and raw event payloads are
# deliberately never returned.
_REMOTE_READ_ONLY = r"""
import json,sqlite3,sys
application_id=sys.argv[1]
db=sqlite3.connect("file:/data/munshi-apply.sqlite?mode=ro",uri=True,timeout=5)
db.execute("PRAGMA query_only=ON")
db.row_factory=sqlite3.Row
def rows(sql,args=()):
    return [dict(r) for r in db.execute(sql,args).fetchall()]
sessions=rows(
    "SELECT session_id,application_id,plan_id,state,checkpoint_id,updated_at "
    "FROM complete_application_sessions WHERE application_id=? "
    "ORDER BY updated_at DESC, session_id DESC LIMIT 2",(application_id,))
# Previous plans leave historical Apply sessions behind. History by itself
# is not a duplicate running application: select the most recently updated
# session, but fail closed when the newest two cannot be ordered by recency.
# This is OBSERVATION only, never authorization for browser execution.
if len(sessions)>1 and sessions[0]["updated_at"] == sessions[1]["updated_at"]:
    print(json.dumps({"state":"AMBIGUOUS","source":"NETCUP_APPLY_DATABASE",
      "reason":"Current Apply session identity is tied; reconcile before acting."}))
    sys.exit(0)
if not sessions:
    print(json.dumps({"state":"NOT_FOUND","source":"NETCUP_APPLY_DATABASE"}))
    sys.exit(0)
session=sessions[0]
sid=session["session_id"]
jobs=rows(
    "SELECT job_id,state,attempt_count,max_attempts,updated_at "
    "FROM complete_application_prepare_jobs WHERE session_id=? "
    "ORDER BY updated_at DESC LIMIT 1",(sid,))
tasks=rows(
    "SELECT control_id,semantic_type,status,checkpoint_id "
    "FROM resolution_tasks WHERE session_id=? "
    "AND status IN ('PENDING','RESOLVING','WAITING_FOR_USER') "
    "ORDER BY updated_at DESC LIMIT 25",(sid,))
events=rows(
    "SELECT event_type,occurred_at "
    "FROM complete_application_execution_events WHERE session_id=? "
    "ORDER BY occurred_at DESC LIMIT 18",(sid,))
counts={}
for label,table in [
  ("final_reviews","final_application_reviews"),
  ("submit_commands","final_submit_commands"),
  ("employer_receipts","application_submission_receipts")]:
    counts[label]=db.execute(
        "SELECT COUNT(*) FROM "+table+" WHERE session_id=?",(sid,)
    ).fetchone()[0]
print(json.dumps({"source":"NETCUP_APPLY_DATABASE","state":"FOUND",
    "application_id":application_id,"session":session,
    "prepare_job":jobs[0] if jobs else None,"pending_controls":tasks,
    "events":events,"counts":counts,"read_only":True},separators=(",",":")))
"""


def reconcile_readonly_hosted_state(result: dict[str, Any]) -> dict[str, Any]:
    """Resolve stale session labels against the authoritative prepare queue.

    Does not write or retry a session. Historical Apply sessions frequently
    retain SESSION_STARTING after their preparation jobs end, so this
    observation must distinguish an actually running browser from a completed
    failed job. Never claim receipt verification based on row counts.
    """
    if result.get("state") != "FOUND":
        return result

    observation = dict(result)
    session = dict(observation.get("session") or {})
    job = dict(observation.get("prepare_job") or {})
    session_state = str(session.get("state") or "").strip().upper()
    job_state = str(job.get("state") or "").strip().upper()

    if job_state in {"FAILED_SAFELY", "BLOCKED", "CANCELLED"}:
        observation["effective_state"] = job_state
        observation["next_action"] = (
            "Inspect the failed preparation and create a fresh, reviewed plan; "
            "do not automatically retry an old employer browser session."
            if job_state == "FAILED_SAFELY" else
            "Inspect the protected checkpoint or cancellation before proceeding."
        )
        observation["session_state_mismatch"] = session_state != job_state
    elif job_state == "WAITING_INPUT":
        observation["effective_state"] = "NEEDS_INPUT"
        observation["next_action"] = (
            "Review unresolved employer questions or protected checkpoints; "
            "the existing run must not submit while input is pending."
        )
        observation["session_state_mismatch"] = session_state != "NEEDS_INPUT"
    elif job_state == "READY_FOR_REVIEW":
        has_review = int((observation.get("counts") or {}).get("final_reviews") or 0) > 0
        observation["effective_state"] = (
            "READY_FOR_REVIEW" if has_review else "REVIEW_NOT_FROZEN"
        )
        observation["next_action"] = (
            "Verify the exact frozen review and authority before final submission."
            if has_review else
            "A preparation job reports review-ready but no frozen review exists."
        )
        observation["session_state_mismatch"] = not has_review
    else:
        observation["effective_state"] = session_state or "UNKNOWN"
        observation["next_action"] = (
            "Continue observing this run; no final submission is confirmed."
        )
        observation["session_state_mismatch"] = False

    observation["submission_verified"] = False
    # A raw count of rows in application_submission_receipts does not provide
    # the independent employer confirmation required by the Hunter ledger.
    return observation


def config_location() -> Path:
    override = os.environ.get("MUNSHI_HOSTED_RUN_MONITOR_CONFIG")
    return Path(override).expanduser() if override else _CONFIG_DEFAULT


def _configured_target() -> tuple[str, str, str]:
    path = config_location()
    if not path.is_file():
        raise ValueError(
            "Hosted-run observer is not configured. Install the owner-only "
            "hosted-monitor.json; the local AutoPilot is not a Netcup status source."
        )
    if path.stat().st_mode & 0o077:
        raise ValueError("Hosted-run monitor configuration must be owner-only (0600).")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Hosted-run monitor configuration must be an object.")
    host = data.get("ssh_host")
    container = data.get("apply_container", "munshi-apply-production-apply-1")
    identity = data.get("ssh_identity_file")
    if not isinstance(host, str) or not _HOST.fullmatch(host):
        raise ValueError("Configured hosted-run SSH destination is invalid.")
    if not isinstance(container, str) or not _CONTAINER.fullmatch(container):
        raise ValueError("Configured hosted-run Apply container is invalid.")
    if not isinstance(identity, str):
        raise ValueError("Configured hosted-run SSH identity is missing.")
    identity_path = Path(identity).expanduser()
    if not identity_path.is_file():
        raise ValueError("Configured hosted-run SSH identity is unavailable.")
    return host, str(identity_path), container


def get_hosted_run_status(payload: Any) -> dict[str, Any]:
    """Observe one immutable application identity; never update server state."""
    if not isinstance(payload, dict) or set(payload) != {"applicationId"}:
        raise ValueError("Hosted-run status requires only applicationId.")
    app_id = payload.get("applicationId")
    if not isinstance(app_id, str) or not _ID.fullmatch(app_id):
        raise ValueError("Hosted-run application identity is invalid.")

    host, identity, container = _configured_target()
    remote = " ".join(
        shlex.quote(part)
        for part in ("docker", "exec", container, "python", "-c", _REMOTE_READ_ONLY, app_id)
    )
    # Fixed command structure, validated identifiers, pinned host, and BatchMode
    # prevent this read-only native probe from becoming a general command runner.
    try:
        completed = subprocess.run(  # noqa: S603
            [
                "/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=7",
                "-i", identity, host, remote,
            ],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        # Do not propagate argv/private filesystem locations from exceptions.
        raise RuntimeError("Canonical hosted-run observer is unavailable.") from None
    if completed.returncode != 0:
        # Do not leak SSH stderr: it could contain environment or private paths.
        raise RuntimeError("Canonical hosted-run observer is unavailable.")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Hosted-run observer returned malformed status.") from exc
    if (
        not isinstance(result, dict)
        or result.get("source") != "NETCUP_APPLY_DATABASE"
        or result.get("state") not in {"FOUND", "NOT_FOUND", "AMBIGUOUS"}
        or (
            result.get("state") == "FOUND"
            and result.get("application_id") != app_id
        )
    ):
        raise RuntimeError("Hosted-run observer returned untrusted application state.")
    return reconcile_readonly_hosted_state(result)
