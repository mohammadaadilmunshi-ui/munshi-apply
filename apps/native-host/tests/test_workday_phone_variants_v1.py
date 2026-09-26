from munshi_apply_native.plan_browser_adapter import PlanBrowserAdapter


def test_phone_variants_preserve_same_us_number():
    values=PlanBrowserAdapter._workday_phone_variants("+1 (856) 555-1212")
    assert "+1 (856) 555-1212" in values
    assert "8565551212" in values
    assert "(856) 555-1212" in values
    assert "856-555-1212" in values


def test_phone_variants_do_not_invent_digits():
    values=PlanBrowserAdapter._workday_phone_variants("856.555.1212")
    normalized={"".join(ch for ch in item if ch.isdigit()) for item in values}
    assert normalized <= {"8565551212"}
