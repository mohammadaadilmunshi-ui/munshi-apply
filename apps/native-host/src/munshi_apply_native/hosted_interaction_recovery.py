"""Hosted-only bounded interaction recovery for pre-submit preparation.

The deterministic PlanBrowserAdapter always runs first. This adapter may only
recover reversible, non-sensitive question controls using the existing
value-free InteractionFallbackService recipe contract. It never navigates or
submits, and a recovery is accepted only after the normal scanner verifies the
field as satisfied. Successful model-assisted mechanics are captured by Teach
MUNSHI off the browser critical path.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

from .execution_policy import prepare_permissions
from .hunter_plan_semantic_bridge import answer_matches_question
from .plan_browser_adapter import (
    NORMAL_AUTOFILL_ENV,
    PlanBrowserAdapter,
    _enabled,
    provider_for_url,
)

_BLOCKED_INPUT_TYPES = {
    "file",
    "password",
    "hidden",
    "submit",
    "button",
    "image",
    "reset",
}
_BLOCKED_ROLES = {"button", "link"}
_ALLOWED_RECOVERY_ACTIONS = {
    "FOCUS",
    "CLICK",
    "TYPE",
    "SELECT_EXACT_OPTION",
    "KEY",
    "WAIT_FOR_STATE",
}
_ALLOWED_KEYS = {"ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"}
_ALLOWED_WAIT_STATES = {"OPTIONS_VISIBLE", "VALUE_COMMITTED"}
_MAX_RECOVERY_ROUNDS = 10

# Teach capture is intentionally serialized and off the browser critical path.
# TeachMunshiService.capture() performs only local validation + a SQLite insert;
# the existing Teach worker performs recipe learning later.
_TEACH_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="munshi-teach-capture",
)


def _dispatch_teach(task: Callable[[], None]) -> None:
    _TEACH_EXECUTOR.submit(task)


def _site_origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Hosted recovery requires an HTTP(S) page origin")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{port}"


def _option_labels(control: dict[str, Any]) -> list[str]:
    raw = control.get("options")
    if not isinstance(raw, list):
        return []
    labels: list[str] = []
    for item in raw[:40]:
        if isinstance(item, dict):
            value = item.get("label") or item.get("text") or item.get("value")
        else:
            value = item
        if value is not None and str(value).strip():
            labels.append(str(value).strip()[:160])
    return labels


def _component_fingerprint(
    *,
    site_origin: str,
    question: dict[str, Any],
    control: dict[str, Any],
) -> str:
    """Stable structural fingerprint that deliberately excludes answer values."""

    identity = {
        "origin": site_origin,
        "semantic": str(question.get("semantic_type") or "UNKNOWN").upper(),
        "question": str(question.get("question") or "").strip().casefold(),
        "name": str(control.get("name") or "").strip().casefold(),
        "label": str(control.get("label") or "").strip().casefold(),
        "role": str(control.get("role") or "").strip().casefold(),
        "inputType": str(control.get("inputType") or "").strip().casefold(),
        "options": [item.casefold() for item in _option_labels(control)],
    }
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "cfp-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:40]


class HostedRecoveringPlanBrowserAdapter(PlanBrowserAdapter):
    """PlanBrowserAdapter with a fail-closed, pre-submit recovery pass."""

    def __init__(
        self,
        *args: Any,
        interaction_fallback_service: Any = None,
        teach_munshi_service: Any = None,
        teach_dispatcher: Callable[[Callable[[], None]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.interaction_fallback_service = interaction_fallback_service
        self.teach_munshi_service = teach_munshi_service
        self.teach_dispatcher = teach_dispatcher or _dispatch_teach

    def prepare_form(
        self,
        *,
        plan: dict[str, Any],
        checkpoint: dict[str, Any] | None,
        resolved_values: dict[str, Any],
    ) -> dict[str, Any]:
        result = super().prepare_form(
            plan=plan,
            checkpoint=checkpoint,
            resolved_values=resolved_values,
        )
        for _round in range(_MAX_RECOVERY_ROUNDS):
            if not self._recovery_enabled(plan, result):
                return result
            recovered = self._recover_unresolved(
                plan=plan,
                result=result,
                resolved_values=resolved_values,
            )
            if not recovered:
                return result
            # Re-enter the deterministic adapter after verified recovery. This
            # keeps the existing scanner/navigation path authoritative. If a
            # later page also has a custom control, the bounded outer loop may
            # recover it only after that deterministic pass has failed first.
            result = super().prepare_form(
                plan=plan,
                checkpoint=checkpoint,
                resolved_values=resolved_values,
            )
        raise ValueError("Hosted recovery exceeded bounded recovery budget")

    def _recovery_enabled(
        self,
        plan: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        if self.interaction_fallback_service is None:
            return False
        if not _enabled(NORMAL_AUTOFILL_ENV):
            return False
        if not prepare_permissions(plan)["normal_answer_autofill"]:
            return False
        if result.get("validation_errors"):
            return False
        unresolved = result.get("unresolved")
        return isinstance(unresolved, list) and bool(unresolved)

    def _recover_unresolved(
        self,
        *,
        plan: dict[str, Any],
        result: dict[str, Any],
        resolved_values: dict[str, Any],
    ) -> bool:
        if self.current_plan(plan) is not True:
            raise ValueError("Hunter plan is stale")
        described = self._scan()
        page = dict(described.get("page") or {})
        controls = {
            str(item.get("controlId")): item
            for item in page.get("controls", [])
            if isinstance(item, dict) and item.get("controlId")
        }
        questions = {
            str(item.get("controlId")): item
            for item in page.get("questions", [])
            if isinstance(item, dict) and item.get("controlId")
        }
        navigation_ids = {
            str(item.get("controlId"))
            for item in page.get("navigationCandidates", [])
            if isinstance(item, dict) and item.get("controlId")
        }
        any_recovered = False
        for unresolved in result.get("unresolved", []):
            if not isinstance(unresolved, dict):
                continue
            control_id = str(unresolved.get("control_id") or "")
            control = controls.get(control_id)
            question = questions.get(control_id)
            if not self._eligible(control_id, control, question, navigation_ids):
                continue
            value = self._answer_value(
                plan=plan,
                question=question,
                control=control,
                resolved_values=resolved_values,
            )
            if value is None:
                continue
            payload = self._fallback_payload(
                question=question,
                control=control,
                failure_reason=str(
                    unresolved.get("reason") or "Deterministic fill failed"
                ),
            )
            proposal: dict[str, Any] | None = None
            recovered = False
            try:
                candidate = self.interaction_fallback_service.propose(payload)
                if isinstance(candidate, dict):
                    proposal = candidate
                    self._execute_actions(
                        control_id=control_id,
                        control=control,
                        actions=proposal.get("actions"),
                        answer=str(value),
                    )
                    recovered = self._field_satisfied(control_id)
            except Exception:
                # Recovery is optional. Any provider, recipe or browser failure
                # preserves the original deterministic unresolved result.
                recovered = False
            if not recovered or proposal is None:
                continue

            any_recovered = True
            self.on_event(
                "FIELD_VERIFIED",
                {
                    "control_id": control_id,
                    "status": "FILLED",
                    "recovered": True,
                },
            )
            self._capture_teach_async(
                plan=plan,
                payload=payload,
                proposal=proposal,
                page=page,
            )
        return any_recovered

    @staticmethod
    def _eligible(
        control_id: str,
        control: dict[str, Any] | None,
        question: dict[str, Any] | None,
        navigation_ids: set[str],
    ) -> bool:
        if not control_id or control_id in navigation_ids or not control or not question:
            return False
        if control.get("visible") is not True or control.get("disabled") is True:
            return False
        if question.get("sensitive") is True:
            return False
        if str(question.get("sensitivity_class") or "NORMAL").upper() != "NORMAL":
            return False
        input_type = str(control.get("inputType") or "").casefold()
        role = str(control.get("role") or "").casefold()
        tag = str(control.get("tagName") or "").casefold()
        if (
            input_type in _BLOCKED_INPUT_TYPES
            or role in _BLOCKED_ROLES
            or tag == "button"
        ):
            return False
        return True

    @staticmethod
    def _answer_value(
        *,
        plan: dict[str, Any],
        question: dict[str, Any],
        control: dict[str, Any],
        resolved_values: dict[str, Any],
    ) -> Any:
        value = resolved_values.get(str(control.get("name") or ""))
        candidates = [
            answer
            for answer in plan.get("answers", [])
            if isinstance(answer, dict)
            and answer.get("autofill_allowed") is True
            and answer.get("sensitivity_class") == "NORMAL"
            and answer.get("execution_value") is not None
            and answer_matches_question(answer, question, control)
        ]
        if value is None and len(candidates) == 1:
            value = candidates[0]["execution_value"]
        return value

    def _fallback_payload(
        self,
        *,
        question: dict[str, Any],
        control: dict[str, Any],
        failure_reason: str,
    ) -> dict[str, Any]:
        origin = _site_origin(self.page.url)
        popup = control.get("hasPopup")
        if popup is None:
            popup = control.get("ariaHasPopup")
        kind = (
            control.get("role")
            or control.get("inputType")
            or control.get("tagName")
            or "INPUT"
        )
        return {
            "siteOrigin": origin,
            "componentFingerprint": _component_fingerprint(
                site_origin=origin,
                question=question,
                control=control,
            ),
            "semanticType": str(question.get("semantic_type") or "UNKNOWN"),
            "controlKind": str(kind),
            "label": str(
                question.get("question") or control.get("label") or ""
            )
            or None,
            "role": str(control.get("role") or "") or None,
            "hasPopup": str(popup) if popup is not None else None,
            "atsFamily": provider_for_url(self.page.url),
            "options": _option_labels(control),
            "failureReason": failure_reason[:500],
            "reversible": True,
            "sensitive": False,
            "authenticationBoundary": False,
            "finalSubmit": False,
        }

    def _execute_actions(
        self,
        *,
        control_id: str,
        control: dict[str, Any],
        actions: Any,
        answer: str,
    ) -> None:
        if not isinstance(actions, list) or not actions or len(actions) > 16:
            raise ValueError("Hosted recovery requires 1-16 bounded actions")
        element = self._element(control_id)
        for raw in actions:
            if (
                not isinstance(raw, dict)
                or raw.get("type") not in _ALLOWED_RECOVERY_ACTIONS
            ):
                raise ValueError("Hosted recovery received an unsupported action")
            action_type = str(raw["type"])
            if action_type == "FOCUS":
                element.focus()
            elif action_type == "CLICK":
                element.click()
            elif action_type == "TYPE":
                if raw.get("valueSource") != "ANSWER":
                    raise ValueError("Hosted recovery TYPE must use ANSWER")
                element.fill(answer)
            elif action_type == "SELECT_EXACT_OPTION":
                self._select_exact_option(element, answer)
            elif action_type == "KEY":
                key = str(raw.get("key") or "")
                if key not in _ALLOWED_KEYS:
                    raise ValueError("Hosted recovery key is not allowed")
                if key == "Enter" and not self._enter_is_safe(control):
                    raise ValueError(
                        "Hosted recovery refuses Enter outside a popup control"
                    )
                element.press(key)
            elif action_type == "WAIT_FOR_STATE":
                state = str(raw.get("state") or "")
                if state not in _ALLOWED_WAIT_STATES:
                    raise ValueError("Hosted recovery wait state is not allowed")
                self._wait_for_state(state, control_id, element, answer)

    def _select_exact_option(self, element: Any, answer: str) -> None:
        tag = str(element.evaluate("element => element.tagName.toLowerCase()"))
        if tag == "select":
            match = element.evaluate(
                """(element, value) => {
                  const option = Array.from(element.options || []).find(
                    item => item.label === value || item.value === value
                  );
                  return option ? option.value : null;
                }""",
                answer,
            )
            if match is None:
                raise ValueError("Exact native option was not found")
            element.select_option(value=str(match))
            return
        option = self.page.get_by_role("option", name=answer, exact=True)
        if option.count() != 1:
            raise ValueError("Exact custom option is missing or ambiguous")
        option.click()

    @staticmethod
    def _enter_is_safe(control: dict[str, Any]) -> bool:
        role = str(control.get("role") or "").casefold()
        popup = str(
            control.get("hasPopup") or control.get("ariaHasPopup") or ""
        ).casefold()
        return role in {"combobox", "listbox"} or popup not in {"", "false", "none"}

    def _wait_for_state(
        self,
        state: str,
        control_id: str,
        element: Any,
        answer: str,
    ) -> None:
        if state == "OPTIONS_VISIBLE":
            tag = str(element.evaluate("element => element.tagName.toLowerCase()"))
            if tag == "select":
                exists = element.evaluate(
                    """(element, value) => Array.from(element.options || []).some(
                      option => option.label === value || option.value === value
                    )""",
                    answer,
                )
                if exists is not True:
                    raise ValueError("Expected native option is unavailable")
                return
            self.page.get_by_role("option", name=answer, exact=True).wait_for(
                state="visible",
                timeout=1500,
            )
            return
        for _attempt in range(20):
            if self._field_satisfied(control_id):
                return
            self.page.wait_for_timeout(50)
        raise ValueError("Recovered value did not commit")

    def _field_satisfied(self, control_id: str) -> bool:
        described = self._scan()
        return any(
            isinstance(field, dict)
            and str(field.get("control_id") or "") == control_id
            and field.get("satisfied") is True
            for field in described.get("fields", [])
        )

    def _capture_teach_async(
        self,
        *,
        plan: dict[str, Any],
        payload: dict[str, Any],
        proposal: dict[str, Any],
        page: dict[str, Any],
    ) -> None:
        if self.teach_munshi_service is None:
            return
        actions = proposal.get("actions")
        teacher_kind = str(proposal.get("teacherKind") or "MODEL").upper()
        provider = proposal.get("provider")
        identity = json.dumps(
            {
                "application": str(plan.get("application_id") or ""),
                "page": str(page.get("pageFingerprint") or ""),
                "component": payload["componentFingerprint"],
                "actions": actions,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        lesson = {
            "observationId": "obs-"
            + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
            "applicationId": str(plan.get("application_id") or "") or None,
            "siteOrigin": payload["siteOrigin"],
            "componentFingerprint": payload["componentFingerprint"],
            "semanticType": payload["semanticType"],
            "atsFamily": payload.get("atsFamily"),
            "teacherKind": teacher_kind,
            "teacherProvider": str(provider) if provider else None,
            "sourceLane": str(
                proposal.get("sourceLane") or "AUTOAPPLY_FALLBACK"
            ),
            "actions": actions,
            "verifiedSuccess": True,
        }

        def capture() -> None:
            try:
                self.teach_munshi_service.capture(lesson)
            except Exception:
                # Learning is deliberately non-blocking after a verified recovery.
                return

        try:
            self.teach_dispatcher(capture)
        except Exception:
            # Dispatch failure must not turn verified recovery into application failure.
            return
