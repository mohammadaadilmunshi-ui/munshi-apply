from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # noqa: S404
from collections.abc import Callable
from pathlib import Path

import httpx

from .autonomous_apply_credentials import (
    AutonomousApplyConfiguration,
    AutonomousApplyCredentialStore,
)
from .mechanics_actions import (
    MechanicsActionError,
    validate_legacy_actions,
    validate_mechanics_actions,
)

_RESULT_PREFIX = "MUNSHI_INTERACTION_RECOVERY="
_BLOCKED_SEMANTIC_MARKERS = {
    "MFA",
    "CAPTCHA",
    "IDENTITY_VERIFICATION",
    "GOVERNMENT_ID",
    "BIOMETRIC",
    "LIVENESS",
    "TOTP",
    "SMS",
    "FINAL_SUBMIT",
}

_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"
_API_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5",
    "haiku": "claude-haiku-4-5-20251001",
}

Runner = Callable[[str, str, str, float, int, str | None], str]
ConfigResolver = Callable[[], AutonomousApplyConfiguration | dict[str, object]]
SecretResolver = Callable[[], str]


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


def _validate_actions(
    value: object,
    *,
    mechanics_mode: bool,
    allowed_target_refs: set[str] | None = None,
    allowed_value_refs: set[str] | None = None,
) -> list[dict[str, object]]:
    try:
        if mechanics_mode:
            return validate_mechanics_actions(
                value,
                allowed_target_refs=allowed_target_refs,
                allowed_value_refs=allowed_value_refs,
            )
        return validate_legacy_actions(value)
    except MechanicsActionError as error:
        raise InteractionFallbackError(str(error)) from error


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


def _anthropic_api_runner(
    prompt: str,
    model: str,
    *,
    max_wall_seconds: int,
    api_key: str,
) -> str:
    resolved_model = _API_MODEL_ALIASES.get(model.strip().casefold(), model.strip())
    if not resolved_model:
        raise InteractionFallbackError("Anthropic API model is not configured")
    try:
        response = httpx.post(
            _ANTHROPIC_MESSAGES_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": resolved_model,
                # Recovery output is one compact JSON action recipe. Keeping the
                # output ceiling low makes runaway cost impossible on this call.
                "max_tokens": 768,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=float(max_wall_seconds),
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise InteractionFallbackError("Anthropic API interaction recovery failed") from error

    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        raise InteractionFallbackError("Anthropic API returned no recovery content")
    text = "\n".join(
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    if not text:
        raise InteractionFallbackError("Anthropic API returned no recovery text")
    return text


def _default_runner(
    prompt: str,
    model: str,
    auth_mode: str,
    max_cost_usd: float,
    max_wall_seconds: int,
    api_key: str | None,
) -> str:
    if auth_mode == "api":
        if not api_key:
            raise InteractionFallbackError("Anthropic API credential is unavailable")
        return _anthropic_api_runner(
            prompt,
            model,
            max_wall_seconds=max_wall_seconds,
            api_key=api_key,
        )

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
    # Subscription mode must never inherit an API key accidentally.
    env.pop("ANTHROPIC_API_KEY", None)
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

    def __init__(
        self,
        runtime_root: Path,
        *,
        runner: Runner | None = None,
        config_resolver: ConfigResolver | None = None,
        api_key_resolver: SecretResolver | None = None,
    ) -> None:
        self.credentials = AutonomousApplyCredentialStore(runtime_root)
        self.runner = runner or _default_runner
        self.config_resolver = config_resolver
        self.api_key_resolver = api_key_resolver

    def _configuration(self) -> AutonomousApplyConfiguration:
        if self.config_resolver is None:
            return self.credentials.load()
        try:
            resolved = self.config_resolver()
            if isinstance(resolved, AutonomousApplyConfiguration):
                return resolved
            if isinstance(resolved, dict):
                return AutonomousApplyConfiguration.from_payload(resolved)
        except Exception as error:
            raise InteractionFallbackError(
                "Autonomous Apply dashboard configuration is unavailable"
            ) from error
        raise InteractionFallbackError(
            "Autonomous Apply dashboard configuration is invalid"
        )

    def _anthropic_api_key(self) -> str:
        if self.api_key_resolver is None:
            try:
                return self.credentials.get_secret("anthropic")
            except Exception as error:
                raise InteractionFallbackError(
                    "Anthropic API credential is unavailable"
                ) from error
        try:
            value = str(self.api_key_resolver() or "").strip()
        except Exception as error:
            raise InteractionFallbackError(
                "Dashboard Anthropic API credential is unavailable"
            ) from error
        if not value or len(value) > 16384:
            raise InteractionFallbackError(
                "Dashboard Anthropic API credential is unavailable"
            )
        return value

    def propose(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise InteractionFallbackError("Interaction recovery payload must be an object")
        if payload.get("reversible") is not True:
            raise InteractionFallbackError("Automatic recovery requires reversible pre-submit mechanics")
        if payload.get("finalSubmit") is not False:
            raise InteractionFallbackError("Final submission cannot use model recovery")
        if payload.get("secretMaterialExposed", False) is not False:
            raise InteractionFallbackError("Secret material must never be exposed to model recovery")
        if payload.get("verificationMaterialExposed", False) is not False:
            raise InteractionFallbackError(
                "Verification artifacts must never be exposed to model recovery"
            )

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
        mechanics_mode = payload.get("mechanicsMode") is True

        config = self._configuration()
        if not config.enabled:
            raise InteractionFallbackError("Autonomous Apply fallback is disabled")
        model = config.model.strip()
        if not model:
            raise InteractionFallbackError("Autonomous Apply fallback model is not configured")
        api_key = self._anthropic_api_key() if config.auth_mode == "api" else None

        surface_value = payload.get("mechanicsSurface")
        mechanics_surface: list[dict[str, object]] = []
        allowed_target_refs: set[str] = set()
        if mechanics_mode:
            if not isinstance(surface_value, list) or not surface_value:
                raise InteractionFallbackError(
                    "Mechanics mode requires an observed mechanics surface"
                )
            if len(surface_value) > 180:
                raise InteractionFallbackError("Mechanics surface is too large")
            for raw_target in surface_value:
                if not isinstance(raw_target, dict):
                    raise InteractionFallbackError("Mechanics targets must be objects")
                target_ref = _required_text(
                    raw_target.get("targetRef"), "targetRef", limit=96
                )
                if not target_ref.startswith("mt-"):
                    raise InteractionFallbackError("Mechanics target ref is invalid")
                allowed_target_refs.add(target_ref)
                mechanics_surface.append(
                    {
                        "targetRef": target_ref,
                        "frameIndex": int(raw_target.get("frameIndex") or 0),
                        "tag": str(raw_target.get("tag") or "")[:40],
                        "type": str(raw_target.get("type") or "")[:80],
                        "role": str(raw_target.get("role") or "")[:80],
                        "name": str(raw_target.get("name") or "")[:120],
                        "id": str(raw_target.get("id") or "")[:120],
                        "label": str(raw_target.get("label") or "")[:180],
                        "ariaLabel": str(raw_target.get("ariaLabel") or "")[:180],
                        "placeholder": str(raw_target.get("placeholder") or "")[:180],
                        "visible": bool(raw_target.get("visible")),
                        "disabled": bool(raw_target.get("disabled")),
                        "required": bool(raw_target.get("required")),
                        "fileInput": bool(raw_target.get("fileInput")),
                        "finalSubmitRisk": bool(raw_target.get("finalSubmitRisk")),
                    }
                )

        refs_value = payload.get("availableRefs")
        available_refs: list[dict[str, str]] = []
        allowed_value_refs: set[str] = set()
        if mechanics_mode:
            if refs_value is not None and not isinstance(refs_value, list):
                raise InteractionFallbackError("availableRefs must be a list")
            for raw_ref in (refs_value or [])[:120]:
                if not isinstance(raw_ref, dict):
                    raise InteractionFallbackError("Mechanics value refs must be objects")
                ref_value = _required_text(raw_ref.get("ref"), "ref", limit=224)
                kind = _required_text(raw_ref.get("kind"), "kind", limit=80).upper()
                allowed_value_refs.add(ref_value)
                available_refs.append({"ref": ref_value, "kind": kind})

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
            "goal": _optional_text(payload.get("goal"), "goal", limit=240),
            "authenticationBoundary": bool(payload.get("authenticationBoundary")),
            "mechanicsSurface": mechanics_surface,
            "availableRefs": available_refs,
        }
        if mechanics_mode:
            prompt = (
                "You are MUNSHI's bounded pre-submit mechanics fallback. "
                "The deterministic Playwright path and promoted Teach recipe have already "
                "failed. You may solve arbitrary REVERSIBLE mechanics before final submit, "
                "including hidden/custom file uploaders, custom dropdowns, buttons, NEXT "
                "navigation, dialogs, date pickers, account/signup/login screens, iframes, "
                "open shadow DOM, expandable panels, cookie dialogs, and unfamiliar ATS UI. "
                "NEVER decide or trigger final submission. NEVER return literal candidate "
                "answers, passwords, secrets, verification codes, verification URLs, CSS/XPath "
                "selectors, or JavaScript. Use only targetRef values from mechanicsSurface and "
                "opaque refs from availableRefs. The trusted executor resolves all values locally. "
                "Allowed actions: FOCUS(targetRef), CLICK(targetRef), NEXT(targetRef), "
                "TYPE_ANSWER_REF(targetRef,answerRef), FILL_SECRET_REF(targetRef,secretRef), "
                "FILL_VERIFICATION_ARTIFACT(targetRef,verificationRef), "
                "UPLOAD_ARTIFACT(targetRef,artifactRef), SELECT(targetRef,valueRef), "
                "KEY(targetRef,key), WAIT_FOR_STATE(state,targetRef optional), and "
                "OPEN_LINK(verificationRef). Do not solve CAPTCHA/MFA/TOTP/SMS/biometric/"
                "government-ID challenges. Keep the sequence minimal and bounded.\nMECHANICS="
                + json.dumps(safe_context, ensure_ascii=False, separators=(",", ":"))
                + f"\nOutput exactly one line: {_RESULT_PREFIX}"
                + '{"actions":[...],"reason":"short mechanics rationale"}'
            )
        else:
            prompt = (
                "You are the bounded interaction-mechanics fallback for MUNSHI AutoApply. "
                "The deterministic executor already failed on one reversible form control. "
                "Return ONLY a value-free action recipe; never invent or repeat the candidate's "
                "answer or submission actions. The trusted executor supplies the approved answer "
                "at runtime. Allowed legacy actions: FOCUS, CLICK, TYPE with valueSource ANSWER, "
                "SELECT_EXACT_OPTION, KEY, WAIT_FOR_STATE. Keep the sequence minimal.\nCONTROL="
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
        actions = _validate_actions(
            proposed.get("actions"),
            mechanics_mode=mechanics_mode,
            allowed_target_refs=allowed_target_refs if mechanics_mode else None,
            allowed_value_refs=allowed_value_refs if mechanics_mode else None,
        )
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
            "secretMaterialSent": False,
            "verificationMaterialSent": False,
            "mechanicsMode": mechanics_mode,
        }
