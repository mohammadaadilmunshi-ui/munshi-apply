from __future__ import annotations

from pathlib import Path

from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


class _Page:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.scripts: list[str] = []
        self.waits: list[int] = []

    def evaluate(self, script, *_args):
        self.scripts.append(str(script))
        if self.error:
            raise self.error
        return self.result

    def wait_for_timeout(self, milliseconds):
        self.waits.append(int(milliseconds))


def _adapter(page: _Page) -> PlanBrowserAdapter:
    return PlanBrowserAdapter(
        page,
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path("unused-runtime.js"),
    )


def test_bounded_cookie_acceptance_is_best_effort_and_emits_safe_event():
    page = _Page({"dismissed": True, "label": "accept all cookies"})
    adapter = _adapter(page)
    events = []
    adapter.on_event = lambda kind, evidence: events.append((kind, evidence))

    assert adapter._dismiss_cookie_consent() is True

    assert len(page.scripts) == 1
    script = page.scripts[0]
    assert "accept all cookies" in script
    assert "tracking technologies" in script
    assert "onetrust" in script
    assert "element.click()" in script
    assert page.waits == [100]
    assert events == [
        (
            "COOKIE_CONSENT_DISMISSED",
            {
                "strategy": "bounded_cookie_accept",
                "label": "accept all cookies",
            },
        )
    ]


def test_cookie_acceptance_failure_never_blocks_application():
    adapter = _adapter(_Page(error=RuntimeError("browser overlay changed")))
    events = []
    adapter.on_event = lambda kind, evidence: events.append((kind, evidence))

    assert adapter._dismiss_cookie_consent() is False
    assert events == []
