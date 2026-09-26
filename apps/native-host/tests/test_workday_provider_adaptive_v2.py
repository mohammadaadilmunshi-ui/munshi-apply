from pathlib import Path

from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


class _EmptyNested:
    @property
    def first(self):
        return self

    def count(self):
        return 0

    def click(self):
        raise AssertionError("empty nested locator must not be clicked")


class _Candidate:
    def __init__(self, page, *, selected=False):
        self.page=page
        self.selected=selected

    def is_visible(self):
        return True

    def evaluate(self, _script):
        return {
            "selectedContainer": self.selected,
            "values": ["Indeed", "Indeed", "", "", "", "", ""],
            "id": "selected" if self.selected else "real-option",
        }

    def locator(self, _selector):
        return _EmptyNested()

    def click(self):
        self.page.clicked += 1


class _Locator:
    def __init__(self, page):
        self.items=[
            _Candidate(page, selected=True),
            _Candidate(page, selected=False),
        ]

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class _TextLocator:
    def count(self):
        return 0

    def nth(self, _index):
        raise AssertionError("no text candidate")


class _Page:
    url="https://example.wd1.myworkdayjobs.com/en-US/job/apply"

    def __init__(self):
        self.clicked=0
        self.elapsed=0

    def locator(self, _selector):
        return _Locator(self)

    def get_by_text(self, _text, *, exact):
        assert exact is True
        return _TextLocator()

    def wait_for_timeout(self, milliseconds):
        self.elapsed += int(milliseconds)


def test_exact_option_ignores_selected_item_and_clicks_real_prompt_option():
    page=_Page()
    adapter=PlanBrowserAdapter(
        page,
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path(__file__),
    )
    assert adapter._workday_click_exact_option("Indeed", timeout_ms=500) is True
    assert page.clicked == 1
