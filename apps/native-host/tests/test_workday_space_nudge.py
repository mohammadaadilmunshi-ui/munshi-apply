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
            "role": "combobox",
            "hasPopup": "listbox",
            "autocomplete": "list",
            "automationId": "promptSearch",
            "id": "source--source",
            "name": "",
        }

    def click(self):
        self.clicks += 1

    def press(self, key):
        self.presses.append(key)

    def type(self, value, delay=0):
        self.types.append((value, delay))


def test_workday_referral_uses_exact_option_without_space_backspace_nudge(monkeypatch):
    page = _Page()
    adapter = PlanBrowserAdapter(
        page,
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path(__file__),
    )
    element = _Element()
    monkeypatch.setattr(adapter, "_element", lambda _control_id: element)

    exact_option_calls = []

    def _click_exact(value, **kwargs):
        exact_option_calls.append((value, kwargs.get("trigger")))
        return value == "Indeed"

    monkeypatch.setattr(adapter, "_workday_click_exact_option", _click_exact)

    # Prompt verification happens before typing, immediately after exact option
    # activation, and once more after blur. Only provider-selected state counts.
    committed = iter((False, True, True))
    monkeypatch.setattr(
        adapter,
        "_workday_prompt_committed",
        lambda _element, _answer: next(committed),
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
    assert result["strategy"] == "WORKDAY_PROVIDER_PROMPT"
    assert result["verification"] == "POST_ACTION_PROVIDER_VERIFIED"
    assert exact_option_calls == [("Indeed", element)]

    # The only typed text is the canonical query. The old blind
    # "space + Backspace" provider nudge must never return.
    assert element.types == [("Indeed", 75)]
    assert element.presses == ["Control+A", "Backspace", "Tab"]
