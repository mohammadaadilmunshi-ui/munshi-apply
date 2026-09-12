#!/usr/bin/env python3
"""MUNSHI apply-only autonomous browser worker.

This is a MUNSHI-authored adapter for the execution pattern proven by
ApplyPilot: Claude Code + Playwright MCP + an isolated Chromium browser.
It deliberately does not use ApplyPilot discovery, scoring, resume tailoring,
cover-letter generation, job database, or answer policy.

No CAPTCHA/MFA/OTP/identity-verification bypass is implemented here. Those
conditions return NEEDS_INPUT. Final submission is permitted only when both the
Application Plan request and local autonomous-apply settings allow it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess  # noqa: S404
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

RESULT_PREFIX = "MUNSHI_RESULT_JSON:"
DEFAULT_CDP_PORT = 9322
ALLOWED_AGENT_STATUSES = {
    "COMPLETED",
    "NEEDS_INPUT",
    "BLOCKED",
    "FAILED_SAFELY",
}
ALLOWED_NEEDS_INPUT = {
    "ANSWER_REQUIRED",
    "SENSITIVE_ANSWER_REQUIRED",
    "CAPTCHA",
    "MFA",
    "OTP",
    "IDENTITY_VERIFICATION",
    "AUTHENTICATION",
    "UNSUPPORTED_CONTROL",
    "POLICY_BLOCK",
}


class WorkerError(RuntimeError):
    """Raised for a safe, expected worker failure."""


@dataclass(frozen=True)
class WorkerSettings:
    model: str = "sonnet"
    headless: bool = False
    max_turns: int = 40
    max_cost_usd: float = 1.0
    allow_final_submit: bool = False
    auth_mode: str = "subscription"


@dataclass
class BrowserProcess:
    process: subprocess.Popen[Any]
    profile_dir: Path
    port: int


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkerError(f"Unable to read JSON: {path}") from error
    if not isinstance(payload, dict):
        raise WorkerError(f"Expected JSON object: {path}")
    return payload


def _runtime_root() -> Path:
    override = os.getenv("MUNSHI_APPLY_RUNTIME_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "MUNSHI Apply"
    if platform.system() == "Windows":
        return Path(os.getenv("LOCALAPPDATA", Path.home())) / "MUNSHI Apply"
    return (
        Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        / "munshi-apply"
    )


def _load_settings() -> WorkerSettings:
    path = _runtime_root() / "settings" / "autonomous-apply.json"
    if not path.exists():
        return WorkerSettings()
    payload = _load_json(path)
    return WorkerSettings(
        model=str(payload.get("model", "sonnet")).strip() or "sonnet",
        headless=bool(payload.get("headless", False)),
        max_turns=max(1, min(200, int(payload.get("maxTurns", 40)))),
        max_cost_usd=max(
            0.0, float(payload.get("maxCostPerApplicationUsd", 1.0))
        ),
        allow_final_submit=bool(payload.get("allowFinalSubmit", False)),
        auth_mode=str(payload.get("authMode", "subscription")),
    )


def _keychain_secret(account: str, service: str) -> str | None:
    if platform.system() != "Darwin":
        return None
    result = subprocess.run(  # noqa: S603
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            account,
            "-s",
            service,
            "-w",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _worker_environment(settings: WorkerSettings) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    if settings.auth_mode == "api":
        key = _keychain_secret(
            "ANTHROPIC_API_KEY", "systems.munshi.apply.autonomous.anthropic"
        ) or env.get("ANTHROPIC_API_KEY")
        if not key:
            raise WorkerError(
                "Anthropic API authentication is selected but no API key is configured"
            )
        env["ANTHROPIC_API_KEY"] = key
    return env


def _validate_sha256(path: Path, expected: str) -> None:
    if not path.exists() or not path.is_file():
        raise WorkerError(f"Required artifact does not exist: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest.lower() != expected.lower():
        raise WorkerError(f"Artifact digest mismatch: {path.name}")


def _validate_request(request: dict[str, Any]) -> None:
    if request.get("schema_version") != "1.0":
        raise WorkerError("Unsupported execution-request schema")
    job = request.get("job")
    if not isinstance(job, dict):
        raise WorkerError("Execution request is missing job")
    url = job.get("url")
    if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"}:
        raise WorkerError("Job URL must be http or https")
    permissions = request.get("permissions")
    if not isinstance(permissions, dict):
        raise WorkerError("Execution request is missing permissions")
    if permissions.get("security_checkpoint_bypass") is not False:
        raise WorkerError("Security-checkpoint bypass must remain false")
    for answer in request.get("answers", []):
        if not isinstance(answer, dict) or answer.get("approved") is not True:
            raise WorkerError("Only approved MUNSHI answers may reach the browser agent")
    context = request.get("execution_context")
    if not isinstance(context, dict):
        raise WorkerError("Execution context is missing")
    if (
        context.get("environment") == "production"
        and os.getenv("MUNSHI_ALLOW_PRODUCTION_AUTONOMOUS") != "1"
    ):
        raise WorkerError("Production autonomous execution is not enabled on this host")

    if context.get("synthetic") is not True:
        artifacts = request.get("artifacts")
        if not isinstance(artifacts, dict):
            raise WorkerError("Execution request is missing artifacts")
        resume = artifacts.get("resume")
        if not isinstance(resume, dict):
            raise WorkerError("Execution request is missing resume artifact")
        _validate_sha256(
            Path(str(resume.get("path", ""))), str(resume.get("sha256", ""))
        )
        cover = artifacts.get("cover_letter")
        if isinstance(cover, dict):
            _validate_sha256(
                Path(str(cover.get("path", ""))), str(cover.get("sha256", ""))
            )


def _chrome_path() -> str:
    override = os.getenv("MUNSHI_CHROME_PATH")
    if override and Path(override).exists():
        return override
    candidates: list[str]
    if platform.system() == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif platform.system() == "Windows":
        roots = [os.getenv("PROGRAMFILES", ""), os.getenv("PROGRAMFILES(X86)", "")]
        candidates = [
            str(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
            for root in roots
            if root
        ]
    else:
        candidates = [
            shutil.which("google-chrome") or "",
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
            shutil.which("microsoft-edge") or "",
        ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise WorkerError("Chrome, Edge, or Chromium was not found")


def _kill_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        if platform.system() == "Windows":
            subprocess.run(  # noqa: S603
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _launch_browser(port: int, headless: bool) -> BrowserProcess:
    profile_dir = _runtime_root() / "autonomous-browser" / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [
        _chrome_path(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-notifications",
        "--disable-save-password-bubble",
        "--window-size=1280,900",
    ]
    if headless:
        command.append("--headless=new")
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if platform.system() != "Windows":
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)  # noqa: S603
    time.sleep(2.5)
    if process.poll() is not None:
        raise WorkerError("Browser exited during startup")
    return BrowserProcess(process=process, profile_dir=profile_dir, port=port)


def _mcp_config(port: int) -> dict[str, Any]:
    return {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": [
                    "-y",
                    "@playwright/mcp@latest",
                    f"--cdp-endpoint=http://127.0.0.1:{port}",
                    "--viewport-size=1280x900",
                ],
            }
        }
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _build_prompt(request: dict[str, Any], allow_submit: bool) -> str:
    job = request["job"]
    artifacts = request.get("artifacts", {})
    resume = artifacts.get("resume") or {}
    cover = artifacts.get("cover_letter") or {}
    approved_answers = [
        {
            "question_key": item.get("question_key"),
            "value": item.get("value"),
            "sensitive": item.get("sensitive", False),
            "provenance": item.get("provenance"),
        }
        for item in request.get("answers", [])
        if isinstance(item, dict) and item.get("approved") is True
    ]
    submit_rule = (
        "You MAY activate the final employer submission control only after all visible "
        "required fields are complete and consistent with the supplied facts."
        if allow_submit
        else "You MUST NOT activate any final employer submission control. Stop immediately before final submission."
    )
    return f"""<role>
You are the bounded MUNSHI browser application executor. Use only the Playwright MCP browser tools supplied to this session.
</role>

<mission>
Open and prepare the exact job application below. MUNSHI already performed discovery, job selection, resume tailoring, and answer approval. Do not redo those stages.
</mission>

<job>
{_json_text(job)}
</job>

<documents>
resume_path={resume.get('path', '')}
cover_letter_path={cover.get('path', '') if cover else ''}
</documents>

<approved_answers>
{_json_text(approved_answers)}
</approved_answers>

<hard_rules>
1. Never invent candidate facts, experience, credentials, work authorization, sponsorship status, salary facts, demographic answers, criminal/background answers, licenses, education, or security clearance.
2. Use the approved answers exactly when the application asks an equivalent question. If no approved answer or unambiguous fact is available, stop and return NEEDS_INPUT.
3. Upload only the document paths supplied above.
4. Do not create shell commands, edit local files, read unrelated local files, access email, or use any tool other than Playwright browser tools.
5. If you encounter CAPTCHA, reCAPTCHA, hCaptcha, Turnstile, FunCaptcha, bot challenge, MFA, OTP, SSO approval, identity verification, or another authentication/security checkpoint, do not bypass it. Return NEEDS_INPUT with the checkpoint type.
6. Do not claim an application was submitted merely because a button was clicked, the URL changed, or generic success text appeared. Report observations for MUNSHI's independent verifier.
7. {submit_rule}
</hard_rules>

<execution>
Navigate to {job['url']}.
Fill forms using the supplied approved facts, upload the supplied resume and cover letter when requested, and navigate ordinary multi-page application steps. For an unknown custom widget, reason from accessible labels, current page state, and visible choices. Verify each important action by re-reading the page state before continuing.
</execution>

<result_format>
At the end, output exactly one line beginning with {RESULT_PREFIX} followed by a compact JSON object containing:
status: one of COMPLETED, NEEDS_INPUT, BLOCKED, FAILED_SAFELY;
claimed_submission: boolean;
reason: short string or null;
needs_input_kind: one of ANSWER_REQUIRED, SENSITIVE_ANSWER_REQUIRED, CAPTCHA, MFA, OTP, IDENTITY_VERIFICATION, AUTHENTICATION, UNSUPPORTED_CONTROL, POLICY_BLOCK, or null;
final_url: current browser URL or null;
provider_application_id: string or null if visibly available;
submission_observation: object or null with method, target, http_status, provider_application_id, completion_marker, response_marker;
observations: array of short factual observations.
Do not put secrets, cookies, tokens, passwords, or full sensitive answers in that JSON.
</result_format>
"""


def _parse_agent_output(lines: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    text_parts: list[str] = []
    usage: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_create_tokens": 0,
        "cost_usd": 0.0,
        "turns": 0,
    }
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            text_parts.append(line)
            continue
        if event.get("type") == "assistant":
            content = event.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
        elif event.get("type") == "result":
            result_text = event.get("result")
            if isinstance(result_text, str):
                text_parts.append(result_text)
            raw_usage = event.get("usage", {})
            if isinstance(raw_usage, dict):
                usage["input_tokens"] = int(raw_usage.get("input_tokens", 0) or 0)
                usage["output_tokens"] = int(raw_usage.get("output_tokens", 0) or 0)
                usage["cache_read_tokens"] = int(
                    raw_usage.get("cache_read_input_tokens", 0) or 0
                )
                usage["cache_create_tokens"] = int(
                    raw_usage.get("cache_creation_input_tokens", 0) or 0
                )
            usage["cost_usd"] = float(event.get("total_cost_usd", 0) or 0)
            usage["turns"] = int(event.get("num_turns", 0) or 0)
    combined = "\n".join(text_parts)
    matches = re.findall(rf"{re.escape(RESULT_PREFIX)}\s*(\{{.*\}})", combined)
    if not matches:
        raise WorkerError("Browser agent did not return a structured MUNSHI result")
    try:
        result = json.loads(matches[-1])
    except json.JSONDecodeError as error:
        raise WorkerError("Browser agent returned invalid result JSON") from error
    if not isinstance(result, dict):
        raise WorkerError("Browser agent result must be an object")
    return result, usage


def _safe_submission_observation(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed = {
        "method",
        "target",
        "http_status",
        "provider_application_id",
        "completion_marker",
        "response_marker",
    }
    return {key: value.get(key) for key in allowed}


def _execution_events(
    *,
    run_id: str,
    result: dict[str, Any],
    claimed_submission: bool,
) -> list[dict[str, Any]]:
    status = str(result.get("status", "FAILED_SAFELY"))
    reason = result.get("reason")
    return [
        {
            "sequence": 1,
            "kind": "WORKER_REQUEST_ACCEPTED",
            "timestamp": _utc_now(),
            "verified": True,
            "control_id": None,
            "question_key": None,
            "artifact_sha256": None,
            "detail": f"Autonomous worker {run_id} accepted the governed MUNSHI request.",
        },
        {
            "sequence": 2,
            "kind": "AGENT_EXECUTION_COMPLETE",
            "timestamp": _utc_now(),
            "verified": not claimed_submission,
            "control_id": None,
            "question_key": None,
            "artifact_sha256": None,
            "detail": str(reason or status),
        },
    ]


def _envelope(
    request: dict[str, Any],
    result: dict[str, Any],
    usage: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    run_id = f"autonomous-{uuid.uuid4()}"
    status = str(result.get("status", "FAILED_SAFELY"))
    if status not in ALLOWED_AGENT_STATUSES:
        status = "FAILED_SAFELY"
    claimed_submission = result.get("claimed_submission") is True
    needs_input: list[dict[str, Any]] = []
    if status == "NEEDS_INPUT":
        kind = str(result.get("needs_input_kind") or "ANSWER_REQUIRED")
        if kind not in ALLOWED_NEEDS_INPUT:
            kind = "ANSWER_REQUIRED"
        needs_input.append(
            {
                "kind": kind,
                "message": str(result.get("reason") or "Owner input is required"),
                "question_key": None,
            }
        )
    observation = _safe_submission_observation(result.get("submission_observation"))
    provider_application_id = result.get("provider_application_id")
    if provider_application_id is None and observation is not None:
        provider_application_id = observation.get("provider_application_id")
    wall_seconds = max(0.0, time.time() - started)
    return {
        "schema_version": "1.0",
        "worker_run_id": run_id,
        "plan_id": request["plan_id"],
        "plan_digest": request["plan_digest"],
        "status": status,
        "final_url": result.get("final_url") or request["job"]["url"],
        "provider": request["job"].get("provider"),
        "provider_application_id": provider_application_id,
        "claimed_submission": claimed_submission,
        "needs_input": needs_input,
        "events": _execution_events(
            run_id=run_id,
            result=result,
            claimed_submission=claimed_submission,
        ),
        "submission_observation": observation,
        "cost": {
            "estimated_total_usd": float(usage.get("cost_usd", 0.0) or 0.0),
            "agent_usd": float(usage.get("cost_usd", 0.0) or 0.0),
            "captcha_usd": 0.0,
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
            "agent_steps": int(usage.get("turns", 0) or 0),
            "wall_seconds": wall_seconds,
        },
    }


def _synthetic_result(request: dict[str, Any], started: float) -> dict[str, Any]:
    run_id = f"autonomous-{uuid.uuid4()}"
    elapsed = max(0.0, time.time() - started)
    return {
        "schema_version": "1.0",
        "worker_run_id": run_id,
        "plan_id": request["plan_id"],
        "plan_digest": request["plan_digest"],
        "status": "COMPLETED",
        "final_url": request["job"]["url"],
        "provider": request["job"].get("provider"),
        "provider_application_id": None,
        "claimed_submission": False,
        "needs_input": [],
        "events": [
            {
                "sequence": 1,
                "kind": "WORKER_REQUEST_ACCEPTED",
                "timestamp": _utc_now(),
                "verified": True,
                "control_id": None,
                "question_key": None,
                "artifact_sha256": None,
                "detail": "Synthetic request validated by apply-only autonomous worker.",
            },
            {
                "sequence": 2,
                "kind": "SYNTHETIC_EXECUTION_COMPLETE",
                "timestamp": _utc_now(),
                "verified": True,
                "control_id": None,
                "question_key": None,
                "artifact_sha256": None,
                "detail": "Browser execution intentionally skipped; no external side effect occurred.",
            },
        ],
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


def _diagnose(settings: WorkerSettings) -> dict[str, Any]:
    claude = shutil.which("claude")
    npx = shutil.which("npx")
    try:
        chrome = _chrome_path()
    except WorkerError:
        chrome = None
    auth_ready = settings.auth_mode == "subscription" or bool(
        _keychain_secret(
            "ANTHROPIC_API_KEY", "systems.munshi.apply.autonomous.anthropic"
        )
        or os.getenv("ANTHROPIC_API_KEY")
    )
    return {
        "claude_cli": claude,
        "npx": npx,
        "chrome": chrome,
        "auth_mode": settings.auth_mode,
        "auth_ready": auth_ready,
        "ready": bool(claude and npx and chrome and auth_ready),
    }


def execute(request_path: Path, *, dry_run: bool, port: int) -> dict[str, Any]:
    started = time.time()
    request = _load_json(request_path)
    _validate_request(request)
    settings = _load_settings()
    permissions = request["permissions"]
    context = request["execution_context"]
    allow_submit = (
        not dry_run
        and context.get("synthetic") is not True
        and permissions.get("final_submit") is True
        and settings.allow_final_submit
    )
    budget = request.get("budget") if isinstance(request.get("budget"), dict) else {}
    requested_cost = float(budget.get("max_ai_cost_usd", settings.max_cost_usd))
    max_cost = (
        min(settings.max_cost_usd, requested_cost)
        if requested_cost >= 0
        else settings.max_cost_usd
    )
    max_turns = min(
        settings.max_turns,
        int(budget.get("max_agent_steps", settings.max_turns)),
    )
    max_wall_seconds = int(budget.get("max_wall_seconds", 300))

    if context.get("synthetic") is True and not os.getenv(
        "MUNSHI_RUN_SYNTHETIC_BROWSER"
    ):
        return _synthetic_result(request, started)

    if not shutil.which("claude"):
        raise WorkerError("Claude Code CLI is not installed")
    if not shutil.which("npx"):
        raise WorkerError("npx is not installed")

    browser = _launch_browser(port, settings.headless)
    try:
        with tempfile.TemporaryDirectory(prefix="munshi-autonomous-") as temp_dir:
            temp = Path(temp_dir)
            mcp_path = temp / "mcp.json"
            mcp_path.write_text(json.dumps(_mcp_config(port)), encoding="utf-8")
            prompt = _build_prompt(request, allow_submit)
            command = [
                "claude",
                "--model",
                settings.model,
                "-p",
                "--mcp-config",
                str(mcp_path),
                "--permission-mode",
                "dontAsk",
                "--allowedTools",
                "mcp__playwright__*",
                "--disallowedTools",
                "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch",
                "--no-session-persistence",
                "--max-turns",
                str(max_turns),
                "--max-budget-usd",
                str(max_cost),
                "--output-format",
                "stream-json",
                "--verbose",
                "-",
            ]
            process = subprocess.Popen(  # noqa: S603
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_worker_environment(settings),
                cwd=temp,
            )
            try:
                stdout, _ = process.communicate(prompt, timeout=max_wall_seconds)
            except subprocess.TimeoutExpired as error:
                _kill_process_tree(process)
                raise WorkerError(
                    "Autonomous browser execution exceeded wall-time budget"
                ) from error
            lines = stdout.splitlines()
            result, usage = _parse_agent_output(lines)
            if usage.get("cost_usd", 0.0) > max_cost + 1e-9:
                raise WorkerError("Autonomous browser execution exceeded AI cost budget")
            if result.get("claimed_submission") is True and not allow_submit:
                raise WorkerError("Agent reported final submission without submit authority")
            return _envelope(request, result, usage, started)
    finally:
        _kill_process_tree(browser.process)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MUNSHI apply-only autonomous browser worker"
    )
    parser.add_argument("request", nargs="?", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT)
    args = parser.parse_args()

    settings = _load_settings()
    if args.diagnose:
        print(json.dumps(_diagnose(settings), indent=2, sort_keys=True))
        return 0
    if args.request is None:
        parser.error("request is required unless --diagnose is used")
    try:
        result = execute(args.request, dry_run=args.dry_run, port=args.port)
    except WorkerError as error:
        print(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "FAILED_SAFELY",
                    "reason": str(error),
                    "claimed_submission": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
