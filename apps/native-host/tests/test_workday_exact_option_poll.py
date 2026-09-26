from pathlib import Path

from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


class _Candidate:
    def __init__(self, page, text="Indeed"):
        self.page = page
        self.text = text

    def is_visible(self):
        return True

    def evaluate(self, _script):
        return [self.text, self.text, "", "", "", "", ""]

    def click(self):
        self.page.clicked += 1


class _Locator:
    def __init__(self, page, *, source):
        self.page = page
        self.source = source
        self.candidate = _Candidate(page)

    def count(self):
        if self.source == "selector":
            return 1 if self.page.elapsed_ms >= self.page.selector_visible_at else 0
        return 1 if self.page.exact_text_visible else 0

    def nth(self, _index):
        return self.candidate


class _Trigger:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        if key == "ArrowDown":
            self.page.arrow_down += 1
            self.page.exact_text_visible = True


class _Page:
    def __init__(self, *, selector_visible_at=200, exact_text_visible=False):
        self.elapsed_ms = 0
        self.clicked = 0
        self.arrow_down = 0
        self.selector_visible_at = selector_visible_at
        self.exact_text_visible = exact_text_visible

    def locator(self, _selector):
        return _Locator(self, source="selector")

    def get_by_text(self, _text, *, exact):
        assert exact is True
        return _Locator(self, source="text")

    def wait_for_timeout(self, milliseconds):
        self.elapsed_ms += int(milliseconds)


def _adapter(page):
    return PlanBrowserAdapter(
        page,
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path(__file__),
    )


def test_workday_exact_option_waits_for_async_suggestion() -> None:
    page = _Page(selector_visible_at=200)
    adapter = _adapter(page)
    assert adapter._workday_click_exact_option(
        "Indeed", timeout_ms=1000, poll_ms=50
    ) is True
    assert page.elapsed_ms >= 200
    assert page.clicked == 1


def test_workday_exact_option_can_activate_search_results_with_arrow_down() -> None:
    page = _Page(selector_visible_at=10_000)
    adapter = _adapter(page)
    trigger = _Trigger(page)
    assert adapter._workday_click_exact_option(
        "Indeed", trigger=trigger, timeout_ms=1000, poll_ms=50
    ) is True
    assert page.arrow_down == 1
    assert page.clicked == 1
