from munshi_apply_native.response_planner import classify_response_intent, plan_job_response


def test_job_specific_intents_and_model_lanes():
    assert (
        classify_response_intent("Why do you want to join our company?", "WHY_COMPANY")
        == "WHY_COMPANY"
    )
    assert (
        plan_job_response(
            "Tell us about a time you solved a hard problem", "BEHAVIORAL_EXAMPLE"
        ).model_lane
        == "STRONG"
    )
    plan = plan_job_response("Why this role?", "WHY_ROLE")
    assert plan.requires_job_context is True
    assert plan.requires_candidate_evidence is True
