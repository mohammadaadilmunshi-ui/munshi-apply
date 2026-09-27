from pathlib import Path

from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


class _Keyboard:
    def press(self, _key):
        return None


class _Page:
    url = "https://example.wd1.myworkdayjobs.com/en-US/job/apply"

    def __init__(self):
        self.keyboard = _Keyboard()
        self.waits = []

    def wait_for_timeout(self, milliseconds):
        self.waits.append(int(milliseconds))


class _Element:
    def __init__(self):
        self.types = []
        self.presses = []
        self.clicks = 0

    def evaluate(self, _script):
        return {
            "tag": "input",
            "type": "text",
            "role": "",
            "hasPopup": "",
            "autocomplete": "off",
            "id": "source--source",
            "name": "",
        }

    def click(self):
        self.clicks += 1

    def press(self, key):
        self.presses.append(key)

    def type(self, value, delay=0):
        self.types.append((value, delay))


def test_workday_referral_emits_space_backspace_nudge(monkeypatch):
    page = _Page()
    adapter = PlanBrowserAdapter(
        page,
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path(__file__),
    )
    element = _Element()
    monkeypatch.setattr(adapter, "_element", lambda _control_id: element)
    monkeypatch.setattr(
        adapter,
        "_workday_click_exact_option",
        lambda value, **kwargs: value == "Indeed",
    )
    monkeypatch.setattr(
        adapter,
        "_wait_for_control_committed",
        lambda _control_id: True,
    )
    result = adapter._workday_fill_control(
        control={"controlId": "ctl-ref", "kind": "INPUT"},
        question={
            "semanticType": "REFERRAL",
            "rawText": "How Did You Hear About Us?",
        },
        value="Indeed",
    )
    assert result["status"] == "FILLED"
    assert element.types[-2:] == [("Indeed", 10), (" ", 25)]
    assert element.presses[-1] == "Backspace"
