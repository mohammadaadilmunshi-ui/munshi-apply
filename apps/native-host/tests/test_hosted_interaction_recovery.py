from __future__ import annotations

import json
import threading
from pathlib import Path

from munshi_apply_native.hosted_interaction_recovery import (
    HostedRecoveringPlanBrowserAdapter,
)
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


class _Page:
    url = "https://boards.greenhouse.io/example/jobs/41"

    def wait_for_timeout(self, _milliseconds):
        return None


class _Fallback:
    def __init__(self, proposal=None, error=None):
        self.proposal = proposal or {
            "actions": [
                {"type": "FOCUS"},
                {"type": "TYPE", "valueSource": "ANSWER"},
            ],
            "provider": "claude",
            "teacherKind": "MODEL",
            "sourceLane": "AUTOAPPLY_FALLBACK",
        }
        self.error = error
        self.payloads = []

    def propose(self, payload):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return self.proposal


class _Teach:
    def __init__(self, error=None):
        self.error = error
        self.lessons = []

    def capture(self, payload):
        self.lessons.append(payload)
        if self.error:
            raise self.error
        return {"queued": True}


class _BlockingTeach:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def capture(self, _payload):
        self.started.set()
        self.release.wait(timeout=2)
        self.finished.set()
        return {"queued": True}


def _plan():
    return {
        "application_id": "application-1",
        "answers": [],
        "permissions": {
            "background_prepare": True,
            "resume_upload": True,
            "normal_answer_autofill": True,
        },
    }


def _unresolved():
    return {
        "unresolved": [
            {
                "question_key": "first_name",
                "control_id": "control-1",
                "question": "First name",
                "semantic_type": "FIRST_NAME",
                "sensitivity": "NORMAL",
                "reason": "Required answer is unresolved",
            }
        ],
        "validation_errors": [],
    }


def _scan(*, sensitive=False):
    return {
        "page": {
            "pageFingerprint": "page-fingerprint-1",
            "controls": [
                {
                    "controlId": "control-1",
                    "name": "first_name",
                    "label": "First name",
                    "role": "textbox",
                    "inputType": "text",
                    "visible": True,
                    "disabled": False,
                    "options": [],
                }
            ],
            "questions": [
                {
                    "controlId": "control-1",
                    "question": "First name",
                    "semantic_type": "FIRST_NAME",
                    "sensitive": sensitive,
                }
            ],
            "navigationCandidates": [],
        },
        "fields": [{"control_id": "control-1", "satisfied": True}],
    }


def _adapter(fallback, teach=None, *, dispatcher=None):
    kwargs = {}
    if dispatcher is not None:
        kwargs["teach_dispatcher"] = dispatcher
    return HostedRecoveringPlanBrowserAdapter(
        _Page(),
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path("unused-plan-runtime.js"),
        interaction_fallback_service=fallback,
        teach_munshi_service=teach,
        **kwargs,
    )


def _make_recovery_succeed(monkeypatch, adapter):
    monkeypatch.setattr(adapter, "_scan", lambda: _scan())
    monkeypatch.setattr(adapter, "_execute_actions", lambda **_kwargs: None)
    monkeypatch.setattr(adapter, "_field_satisfied", lambda _control_id: True)


def test_deterministic_success_never_calls_fallback(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback()
    adapter = _adapter(fallback)
    success = {"unresolved": [], "validation_errors": []}
    monkeypatch.setattr(
        PlanBrowserAdapter,
        "prepare_form",
        lambda self, **kwargs: success,
    )

    assert adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={},
    ) is success
    assert fallback.payloads == []


def test_verified_recovery_teaches_without_answer_leak(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback()
    teach = _Teach()
    adapter = _adapter(fallback, teach, dispatcher=lambda task: task())
    initial = _unresolved()
    verified = {"unresolved": [], "validation_errors": []}
    calls = []

    def deterministic(_self, **_kwargs):
        calls.append(1)
        return initial if len(calls) == 1 else verified

    monkeypatch.setattr(PlanBrowserAdapter, "prepare_form", deterministic)
    _make_recovery_succeed(monkeypatch, adapter)
    executed = []
    monkeypatch.setattr(
        adapter,
        "_execute_actions",
        lambda **kwargs: executed.append(kwargs),
    )

    result = adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={"first_name": "Aadil"},
    )

    assert result is verified
    assert len(calls) == 2
    assert len(fallback.payloads) == 1
    assert "Aadil" not in json.dumps(fallback.payloads[0], sort_keys=True)
    assert fallback.payloads[0]["finalSubmit"] is False
    assert fallback.payloads[0]["authenticationBoundary"] is False
    assert executed[0]["answer"] == "Aadil"
    assert len(teach.lessons) == 1
    assert teach.lessons[0]["verifiedSuccess"] is True
    assert teach.lessons[0]["actions"] == fallback.proposal["actions"]


def test_teach_capture_is_dispatched_off_critical_path(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback()
    teach = _BlockingTeach()
    adapter = _adapter(fallback, teach)
    initial = _unresolved()
    verified = {"unresolved": [], "validation_errors": []}
    calls = []

    def deterministic(_self, **_kwargs):
        calls.append(1)
        return initial if len(calls) == 1 else verified

    monkeypatch.setattr(PlanBrowserAdapter, "prepare_form", deterministic)
    _make_recovery_succeed(monkeypatch, adapter)

    result = adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={"first_name": "Aadil"},
    )
    try:
        assert result is verified
        assert teach.started.wait(timeout=1)
        assert teach.finished.is_set() is False
    finally:
        teach.release.set()
        assert teach.finished.wait(timeout=1)


def test_teach_failure_cannot_fail_verified_recovery(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback()
    teach = _Teach(error=RuntimeError("sqlite unavailable"))
    adapter = _adapter(fallback, teach, dispatcher=lambda task: task())
    initial = _unresolved()
    verified = {"unresolved": [], "validation_errors": []}
    calls = []

    def deterministic(_self, **_kwargs):
        calls.append(1)
        return initial if len(calls) == 1 else verified

    monkeypatch.setattr(PlanBrowserAdapter, "prepare_form", deterministic)
    _make_recovery_succeed(monkeypatch, adapter)

    assert adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={"first_name": "Aadil"},
    ) is verified
    assert len(teach.lessons) == 1


def test_later_step_gets_its_own_deterministic_first_recovery(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback()
    adapter = _adapter(fallback)
    unresolved_first = _unresolved()
    unresolved_later = _unresolved()
    verified = {"unresolved": [], "validation_errors": []}
    results = [unresolved_first, unresolved_later, verified]

    def deterministic(_self, **_kwargs):
        return results.pop(0)

    monkeypatch.setattr(PlanBrowserAdapter, "prepare_form", deterministic)
    _make_recovery_succeed(monkeypatch, adapter)

    assert adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={"first_name": "Aadil"},
    ) is verified
    assert len(fallback.payloads) == 2


def test_fallback_error_preserves_original_unresolved_result(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback(error=ValueError("fallback disabled"))
    teach = _Teach()
    adapter = _adapter(fallback, teach, dispatcher=lambda task: task())
    initial = _unresolved()
    monkeypatch.setattr(
        PlanBrowserAdapter,
        "prepare_form",
        lambda self, **kwargs: initial,
    )
    monkeypatch.setattr(adapter, "_scan", lambda: _scan())

    result = adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={"first_name": "Aadil"},
    )

    assert result is initial
    assert len(fallback.payloads) == 1
    assert teach.lessons == []


def test_unknown_recovery_action_fails_closed(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback(proposal={"actions": [{"type": "NAVIGATE"}]})
    adapter = _adapter(fallback)
    initial = _unresolved()
    monkeypatch.setattr(
        PlanBrowserAdapter,
        "prepare_form",
        lambda self, **kwargs: initial,
    )
    monkeypatch.setattr(adapter, "_scan", lambda: _scan())
    monkeypatch.setattr(adapter, "_element", lambda _control_id: object())

    assert adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={"first_name": "Aadil"},
    ) is initial


def test_sensitive_question_never_invokes_fallback(monkeypatch):
    monkeypatch.setenv("MUNSHI_APPLY_NORMAL_ANSWER_AUTOFILL_ENABLED", "true")
    fallback = _Fallback()
    adapter = _adapter(fallback)
    initial = _unresolved()
    monkeypatch.setattr(
        PlanBrowserAdapter,
        "prepare_form",
        lambda self, **kwargs: initial,
    )
    monkeypatch.setattr(adapter, "_scan", lambda: _scan(sensitive=True))

    assert adapter.prepare_form(
        plan=_plan(),
        checkpoint=None,
        resolved_values={"first_name": "Aadil"},
    ) is initial
    assert fallback.payloads == []


def test_enter_is_only_allowed_for_popup_controls():
    assert HostedRecoveringPlanBrowserAdapter._enter_is_safe(
        {"role": "textbox"}
    ) is False
    assert HostedRecoveringPlanBrowserAdapter._enter_is_safe(
        {"role": "combobox"}
    ) is True
    assert HostedRecoveringPlanBrowserAdapter._enter_is_safe(
        {"hasPopup": "listbox"}
    ) is True
