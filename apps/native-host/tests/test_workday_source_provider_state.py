from pathlib import Path
from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter

class _Page:
    url="https://example.wd1.myworkdayjobs.com/en-US/job/apply"

class _Element:
    def evaluate(self, script, arg=None):
        if "selectedItem" in script:
            return "Indeed"
        return False

def test_workday_source_selected_item_is_committed():
    adapter=PlanBrowserAdapter(
        _Page(),
        artifact_reader=lambda _plan: b"",
        current_plan=lambda _plan: True,
        runtime_path=Path(__file__),
    )
    element=_Element()
    assert adapter._workday_source_selected_value(element,"Indeed")=="Indeed"
    assert adapter._workday_source_committed(element,"Indeed") is True
    assert adapter._workday_source_committed(element,"LinkedIn") is False
