from pathlib import Path

from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


class _Candidate:
    def __init__(self, page):
        self.page = page
    def is_visible(self):
        return True
    def evaluate(self, _script):
        return ["Indeed", "", "", ""]
    def click(self):
        self.page.clicked += 1


class _Locator:
    def __init__(self, page):
        self.page = page
        self.candidate = _Candidate(page)
    def count(self):
        return 1 if self.page.elapsed_ms >= 200 else 0
    def nth(self, _index):
        return self.candidate


class _Page:
    def __init__(self):
        self.elapsed_ms = 0
        self.clicked = 0
    def locator(self, _selector):
        return _Locator(self)
    def wait_for_timeout(self, milliseconds):
        self.elapsed_ms += int(milliseconds)


def test_workday_exact_option_waits_for_async_suggestion() -> None:
    page = _Page()
    adapter = PlanBrowserAdapter(
        page,
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path(__file__),
    )
    assert adapter._workday_click_exact_option(
        "Indeed", timeout_ms=1000, poll_ms=50
    ) is True
    assert page.elapsed_ms >= 200
    assert page.clicked == 1
