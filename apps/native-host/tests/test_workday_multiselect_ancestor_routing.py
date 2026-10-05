from pathlib import Path

from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


class _Handle:
    def __init__(self, element) -> None:
        self._element = element

    def as_element(self):
        return self._element


class _Page:
    url = "https://example.wd1.myworkdayjobs.com/en-US/job/apply"

    def __init__(self, element) -> None:
        self.element = element

    def evaluate_handle(self, script, arg=None):
        return _Handle(self.element)

    def wait_for_timeout(self, milliseconds):
        return None


class _Element:
    """Fake Playwright element for the Workday multiselect referral control."""

    def __init__(self, metadata: dict, selected_value: str = "Indeed") -> None:
        self._metadata = dict(metadata)
        self._selected_value = selected_value
        self.calls: list[str] = []

    def evaluate(self, script, arg=None):
        if "ancestorAutomationIds" in script:
            return dict(self._metadata)
        if "selectedItem" in script:
            return self._selected_value
        return False

    def click(self):
        self.calls.append("click")

    def press(self, key, **kwargs):
        self.calls.append(f"press:{key}")

    def type(self, value, **kwargs):
        self.calls.append(f"type:{value}")


def _adapter(element: _Element) -> PlanBrowserAdapter:
    return PlanBrowserAdapter(
        _Page(element),
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path(__file__),
    )


def _control() -> dict:
    return {"controlId": "ctl-fixture-referral", "kind": "TEXT", "name": ""}


def _question() -> dict:
    return {"semanticType": "REFERRAL", "rawText": "How Did You Hear About Us?*"}


def _metadata(ancestor_automation_ids: list[str]) -> dict:
    return {
        "tag": "input",
        "type": "text",
        "role": "",
        "hasPopup": "",
        "autocomplete": "",
        "automationId": "",
        "id": "source--source",
        "name": "",
        "ancestorAutomationIds": ancestor_automation_ids,
    }


def test_workday_multiselect_ancestor_routes_into_prompt_machinery():
    """The exact observed Crescent metadata routes to the prompt verifier.

    The input carries no ARIA prompt semantics of its own; only the
    multiselectInputContainer / multiSelectContainer ancestor wrappers
    identify the Workday component.
    """
    element = _Element(
        _metadata(["multiselectinputcontainer", "multiselectcontainer"])
    )
    adapter = _adapter(element)
    result = adapter._workday_fill_control(
        control=_control(), question=_question(), value="Indeed"
    )
    assert result == {
        "status": "FILLED",
        "reason": "Workday prompt already has the exact selected item",
        "strategy": "WORKDAY_PROMPT_SELECTED_ITEM",
        "verification": "POST_ACTION_PROVIDER_VERIFIED",
    }


def test_plain_text_input_without_multiselect_ancestors_keeps_text_lane():
    """Without Workday multiselect ancestors the plain-text lane is preserved."""
    element = _Element(_metadata([]), selected_value="")
    adapter = _adapter(element)
    adapter._wait_for_control_committed = lambda control_id, **_kwargs: True
    result = adapter._workday_fill_control(
        control=_control(), question=_question(), value="Indeed"
    )
    assert result["status"] == "FILLED"
    assert result["strategy"] == "WORKDAY_TRUSTED_PLAYWRIGHT"
    assert "type:Indeed" in element.calls
