from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # noqa: S404
from collections.abc import Callable
from pathlib import Path

from .autonomous_apply_credentials import AutonomousApplyCredentialStore

_RESULT_PREFIX = "MUNSHI_INTERACTION_RECOVERY="
_BLOCKED_SEMANTIC_MARKERS = {
    "PASSWORD",
    "OTP",
    "MFA",
    "CAPTCHA",
    "IDENTITY_VERIFICATION",
    "AUTHENTICATION",
    "SUBMIT",
    "GOVERNMENT_ID",
    "SMS",
}
_BLOCKED_CONTROL_KINDS = {"FILE", "BUTTON"}
_ALLOWED_KEYS = {"ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"}
_ALLOWED_WAIT_STATES = {"OPTIONS_VISIBLE", "VALUE_COMMITTED"}

Runner = Callable[[str, str, str, float, int, str | None], str]


class InteractionFallbackError(ValueError):
    """A control is not eligible for automatic model-assisted recovery."""


def _required_text(value: object, label: str, *, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InteractionFallbackError(f"{label} must be a non-empty string")
    clean = value.strip()
    if len(clean) > limit:
        raise InteractionFallbackError(f"{label} is too long")
    return clean


def _optional_text(value: object, label: str, *, limit: int = 500) -> str | None:
    if value is None or value == "":
        return None
    return _required_text(value, label, limit=limit)


def _validate_actions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise InteractionFallbackError("Fallback must return 1-16 bounded actions")
    result: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise InteractionFallbackError("Fallback actions must be objects")
        action_type = raw.get("type")
        if action_type in {"FOCUS", "CLICK", "SELECT_EXACT_OPTION"}:
            result.append({"type": str(action_type)})
            continue
        if action_type == "TYPE" and raw.get("valueSource") == "ANSWER":
            result.append({"type": "TYPE", "valueSource": "ANSWER"})
            continue
        if action_type == "KEY" and raw.get("key") in _ALLOWED_KEYS:
            result.append({"type": "KEY", "key": str(raw["key"])})
            continue
        if action_type == "WAIT_FOR_STATE" and raw.get("state") in _ALLOWED_WAIT_STATES:
            result.append({"type": "WAIT_FOR_STATE", "state": str(raw["state"])})
            continue
        raise InteractionFallbackError(
            "Fallback proposed an unsupported or value-bearing action"
        )
    return result


def _parse_output(stdout: str) -> dict[str, object]:
    parts: list[str] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parts.append(line)
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "assistant":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
        elif event.get("type") == "result" and isinstance(event.get("result"), str):
            parts.append(str(event["result"]))
    joined = "\n".join(parts)
    matches = re.findall(rf"{re.escape(_RESULT_PREFIX)}\s*(\{{.*\}})", joined)
    if not matches:
        raise InteractionFallbackError("Fallback solver returned no structured recovery")
    try:
        payload = json.loads(matches[-1])
    except json.JSONDecodeError as error:
        raise InteractionFallbackError("Fallback solver returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise InteractionFallbackError("Fallback solver result must be an object")
    return payload


def _default_runner(
    prompt: str,
    model: str,
    auth_mode: str,
    max_cost_usd: float,
    max_wall_seconds: int,
    api_key: str | None,
) -> str:
    claude = shutil.which("claude")
    if not claude:
        raise InteractionFallbackError("Claude CLI is unavailable for automatic recovery")
    command = [
        claude,
        "--model",
        model,
        "-p",
        "--permission-mode",
        "dontAsk",
        "--disallowedTools",
        "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Read,Grep,Glob",
        "--no-session-persistence",
        "--max-turns",
        "1",
        "--max-budget-usd",
        str(max_cost_usd),
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    ]
    env = os.environ.copy()
    if auth_mode == "subscription":
        env.pop("ANTHROPIC_API_KEY", None)
    elif api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    process = subprocess.run(  # noqa: S603
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=max_wall_seconds,
        check=False,
        env=env,
    )
    stdout = "\n".join(part for part in (process.stdout, process.stderr) if part)
    if process.returncode != 0:
        raise InteractionFallbackError("Automatic interaction recovery solver failed")
    return stdout


class InteractionFallbackService:
    """Proposes bounded value-free mechanics after deterministic browser failure.

    The model never receives the candidate answer value or credentials. It can only
    propose mechanics that the extension executes and verifies in the existing tab.
    Successful mechanics are learned later through the asynchronous Teach MUNSHI
    queue; this service never teaches and therefore never makes a second model call.
    """

    def __init__(self, runtime_root: Path, *, runner: Runner | None = None) -> None:
        self.credentials = AutonomousApplyCredentialStore(runtime_root)
        self.runner = runner or _default_runner

    def propose(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise InteractionFallbackError("Interaction recovery payload must be an object")
        if payload.get("reversible") is not True:
            raise InteractionFallbackError("Automatic recovery requires a reversible control")
        if payload.get("sensitive") is not False:
            raise InteractionFallbackError("Sensitive controls cannot use model recovery")
        if payload.get("authenticationBoundary") is not False:
            raise InteractionFallbackError("Authentication boundaries cannot use model recovery")
        if payload.get("finalSubmit") is not False:
            raise InteractionFallbackError("Final submission cannot use model recovery")

        component_fingerprint = _required_text(
            payload.get("componentFingerprint"), "componentFingerprint", limit=240
        )
        if not component_fingerprint.startswith("cfp-"):
            raise InteractionFallbackError("componentFingerprint is invalid")
        semantic_type = _required_text(
            payload.get("semanticType"), "semanticType", limit=120
        ).upper()
        if any(marker in semantic_type for marker in _BLOCKED_SEMANTIC_MARKERS):
            raise InteractionFallbackError("Security controls cannot use automatic recovery")
        control_kind = _required_text(
            payload.get("controlKind"), "controlKind", limit=80
        ).upper()
        if control_kind in _BLOCKED_CONTROL_KINDS:
            raise InteractionFallbackError(
                "This control kind is not eligible for mechanics recovery"
            )

        config = self.credentials.load()
        if not config.enabled:
            raise InteractionFallbackError("Autonomous Apply fallback is disabled")
        model = config.model.strip()
        if not model:
            raise InteractionFallbackError("Autonomous Apply fallback model is not configured")
        api_key = (
            self.credentials.get_secret("anthropic")
            if config.auth_mode == "api"
            else None
        )

        safe_context = {
            "siteOrigin": _required_text(
                payload.get("siteOrigin"), "siteOrigin", limit=500
            ),
            "componentFingerprint": component_fingerprint,
            "semanticType": semantic_type,
            "controlKind": control_kind,
            "label": _optional_text(payload.get("label"), "label", limit=500),
            "role": _optional_text(payload.get("role"), "role", limit=120),
            "hasPopup": _optional_text(
                payload.get("hasPopup"), "hasPopup", limit=120
            ),
            "atsFamily": _optional_text(
                payload.get("atsFamily"), "atsFamily", limit=80
            ),
            "options": [str(item)[:160] for item in payload.get("options", [])[:40]]
            if isinstance(payload.get("options"), list)
            else [],
            "failureReason": _optional_text(
                payload.get("failureReason"), "failureReason", limit=500
            ),
        }
        prompt = (
            "You are the bounded interaction-mechanics fallback for MUNSHI "
            "AutoApply. "
            "The deterministic executor already failed on one reversible, "
            "non-sensitive form control. "
            "Return ONLY a value-free action recipe; never invent or repeat the "
            "candidate's answer, credentials, OTPs, secrets, identity data, or "
            "submission actions. The extension supplies the approved answer at "
            "runtime when TYPE(valueSource=ANSWER) or SELECT_EXACT_OPTION is used. "
            "Allowed actions: FOCUS, CLICK, TYPE with valueSource ANSWER, "
            "SELECT_EXACT_OPTION, KEY with ArrowDown/ArrowUp/Enter/Tab/Escape, "
            "WAIT_FOR_STATE with OPTIONS_VISIBLE/VALUE_COMMITTED. Do not navigate, "
            "submit, bypass authentication, solve CAPTCHA, or interact with "
            "government ID. Keep the sequence minimal and bounded.\nCONTROL="
            + json.dumps(safe_context, ensure_ascii=False, separators=(",", ":"))
            + f"\nOutput exactly one line: {_RESULT_PREFIX}"
            + '{"actions":[...],"reason":"short mechanics rationale"}'
        )
        stdout = self.runner(
            prompt,
            model,
            config.auth_mode,
            min(max(config.max_cost_per_application_usd, 0.01), 0.15),
            30,
            api_key,
        )
        proposed = _parse_output(stdout)
        actions = _validate_actions(proposed.get("actions"))
        reason = _optional_text(proposed.get("reason"), "reason", limit=500)
        return {
            "actions": actions,
            "reason": reason or "Bounded model-assisted mechanics recovery",
            "provider": "claude",
            "model": model,
            "teacherKind": "MODEL",
            "sourceLane": "AUTOAPPLY_FALLBACK",
            "providerCallMade": True,
            "valueBearingInputSent": False,
        }
