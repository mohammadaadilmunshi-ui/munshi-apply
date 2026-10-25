from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

import pytest

from munshi_apply_native.native_form_learning_v1 import (
    finalize_action,
    native_learning_snapshot,
    observe_action,
    summarize_actions,
)


def _action():
    return observe_action(
        question={
            "semanticType": "WORK_AUTHORIZATION",
            "question": "Will you require sponsorship? sensitive@example.com",
        },
        control={
            "name": "candidate_private_account_reference",
            "label": "Work authorization",
            "inputType": "text",
        },
        result={
            "status": "FILLED",
            "strategy": "GENERIC_RUNTIME",
            "value": "private-answer-that-must-not-be-saved",
        },
        ats_family="WORKDAY",
        sensitivity="NORMAL",
    )


def test_native_learning_observes_structure_but_never_answer_or_label():
    record = _action()
    assert record is not None
    assert len(record["field_fingerprint"]) == 64
    assert record["semantic_type"] == "WORK_AUTHORIZATION"
    assert record["control_kind"] == "text"
    assert record["verification_status"] == "UNVERIFIED"
    dump = json.dumps(record)
    for private in (
        "sensitive@example.com",
        "candidate_private_account_reference",
        "private-answer-that-must-not-be-saved",
        "Work authorization",
    ):
        assert private not in dump


@pytest.mark.parametrize("sensitivity", ["PROTECTED", "SELF_ID", "SECRET"])
def test_protected_fields_are_not_learned(sensitivity):
    assert (
        observe_action(
            question={"semanticType": "WORK_AUTHORIZATION"},
            control={"inputType": "text"},
            result={"status": "FILLED"},
            ats_family="WORKDAY",
            sensitivity=sensitivity,
        )
        is None
    )


@pytest.mark.parametrize("semantic", ["MFA", "CAPTCHA", "LEGAL_ATTESTATION", "FINAL_SUBMIT"])
def test_security_controls_are_not_learned(semantic):
    assert (
        observe_action(
            question={"semanticType": semantic},
            control={"inputType": "text"},
            result={"status": "FILLED"},
            ats_family="WORKDAY",
            sensitivity="NORMAL",
        )
        is None
    )


def test_post_scan_verification_is_required():
    record = _action()
    assert record is not None
    assert finalize_action(record, committed=True)["verification_status"] == "POST_SCAN_COMMITTED"
    assert finalize_action(record, committed=False)["verification_status"] == "UNVERIFIED"
    failed = {**record, "attempt_status": "FAILED"}
    assert finalize_action(failed, committed=True)["verification_status"] == "UNVERIFIED"


def test_learning_hypothesis_requires_three_distinct_verified_applications():
    action = finalize_action(_action(), committed=True)
    first = summarize_actions(
        [
            {"session_id": "s1", "application_id": "a1", "actions": [action, action]},
            {"session_id": "s2", "application_id": "a2", "actions": [action]},
        ]
    )
    assert first["shadow_hypotheses"] == []
    complete = summarize_actions(
        [
            {"session_id": session, "application_id": f"a{index}", "actions": [action]}
            for index, session in enumerate(("s1", "s2", "s3"), start=1)
        ]
    )
    assert len(complete["shadow_hypotheses"]) == 1
    assert complete["shadow_hypotheses"][0]["state"] == "SHADOW_ONLY"
    assert complete["portable_shadow_hypotheses"][0]["ats_family"] == "WORKDAY"
    assert complete["portable_shadow_hypotheses"][0]["verified_applications"] == 3
    assert complete["held_out_self_test_queue"][0]["next_self_test"] == (
        "HELD_OUT_SHADOW_REPLAY_REQUIRED"
    )
    assert complete["held_out_self_test_queue"][0]["submission_authorized"] is False
    assert complete["executable_rules_promoted"] == 0
    assert complete["submission_authorized"] is False
    assert complete["answer_values_stored"] is False
    unverified = finalize_action(_action(), committed=False)
    regressed = summarize_actions(
        [
            {"session_id": session, "application_id": f"a{index}", "actions": [action]}
            for index, session in enumerate(("s1", "s2", "s3"), start=1)
        ]
        + [{"session_id": "s4", "application_id": "a4", "actions": [unverified]}]
    )
    assert regressed["shadow_hypotheses"] == []
    assert regressed["portable_shadow_hypotheses"] == []


def test_multiple_sessions_on_one_application_cannot_create_a_shadow_rule():
    action = finalize_action(_action(), committed=True)
    digest = summarize_actions(
        [
            {
                "session_id": f"s{index}",
                "plan_id": f"replacement-plan-{index}",
                "application_id": "one-job",
                "actions": [action],
            }
            for index in range(8)
        ]
    )
    assert digest["post_scan_verified_actions"] == 8
    assert digest["shadow_hypotheses"] == []
    assert digest["portable_shadow_hypotheses"] == []


def test_untrusted_learning_payload_is_ignored_without_executing():
    outcome = summarize_actions(
        [
            {
                "session_id": "s1",
                "actions": [
                    {
                        "version": "malicious",
                        "field_fingerprint": "a" * 64,
                        "strategy": "FINAL_SUBMIT",
                        "verification_status": "POST_SCAN_COMMITTED",
                    }
                ],
            },
            {"session_id": "", "actions": [{}]},
        ]
    )
    assert outcome["observed_action_attempts"] == 0
    assert outcome["shadow_hypotheses"] == []


def test_claimed_committed_field_is_not_verified_if_action_itself_failed():
    impossible = {
        **finalize_action(_action(), committed=True),
        "attempt_status": "FAILED",
    }
    result = summarize_actions(
        [
            {
                "session_id": f"s{index}",
                "application_id": f"a{index}",
                "actions": [impossible],
            }
            for index in range(3)
        ]
    )
    assert result["post_scan_verified_actions"] == 0
    assert result["shadow_hypotheses"] == []
    assert result["portable_shadow_hypotheses"] == []


def test_minimum_support_cannot_be_lowered():
    with pytest.raises(ValueError):
        summarize_actions([], min_distinct_applications=2)


def test_self_test_queue_prioritizes_unverified_actions_without_applicant_data():
    good = finalize_action(_action(), committed=True)
    failed = finalize_action(_action(), committed=False)
    digest = summarize_actions(
        [
            {"session_id": "s1", "application_id": "a1", "actions": [good]},
            {"session_id": "s2", "application_id": "a2", "actions": [failed]},
        ]
    )
    assert digest["held_out_self_test_queue"] == [
        {
            "ats_family": "WORKDAY",
            "observed_action_attempts": 2,
            "post_scan_verified_actions": 1,
            "unverified_action_attempts": 1,
            "distinct_verified_applications": 1,
            "observed_control_kinds": ["text"],
            "next_self_test": "REPLAY_UNVERIFIED_CONTROLS_IN_ISOLATED_BROWSER",
            "submission_authorized": False,
        }
    ]
    assert "sensitive@example.com" not in json.dumps(digest)


def test_native_learning_snapshot_counts_only_native_verified_receipts():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE career_os_application_plans ("
        "plan_id TEXT,tenant_id TEXT,user_id TEXT,application_id TEXT)"
    )
    conn.execute(
        "CREATE TABLE complete_application_execution_events ("
        "event_id TEXT,session_id TEXT,plan_id TEXT,event_type TEXT,"
        "evidence_json TEXT,occurred_at TEXT)"
    )
    conn.execute("CREATE TABLE final_submit_commands (command_id TEXT,plan_id TEXT)")
    conn.execute(
        "CREATE TABLE application_submission_receipts (verification_status TEXT,plan_id TEXT)"
    )
    conn.execute("INSERT INTO career_os_application_plans VALUES ('p1','t1','u1','a1')")
    conn.execute("INSERT INTO career_os_application_plans VALUES ('p2','t2','u2','a2')")
    conn.execute("INSERT INTO career_os_application_plans VALUES ('p3','t1','u1','a3')")
    conn.execute("INSERT INTO career_os_application_plans VALUES ('p4','t1','u1','a4')")
    action = finalize_action(_action(), committed=True)
    for i in range(3):
        conn.execute(
            "INSERT INTO complete_application_execution_events VALUES (?,?,?,?,?,?)",
            (
                f"e{i}",
                f"s{i}",
                ("p1", "p3", "p4")[i],
                "FORM_PREPARED",
                json.dumps(
                    {"native_field_learning_evidence": [action], "private_answer": "must-not-leak"}
                ),
                f"2026-10-25T00:0{i}:00+00:00",
            ),
        )
    conn.execute("INSERT INTO final_submit_commands VALUES ('command1','p1')")
    conn.execute("INSERT INTO final_submit_commands VALUES ('other-owner','p2')")
    conn.execute("INSERT INTO application_submission_receipts VALUES ('VERIFIED','p1')")
    conn.execute("INSERT INTO application_submission_receipts VALUES ('VERIFIED','p2')")
    conn.execute(
        "INSERT INTO application_submission_receipts VALUES ('SUBMISSION_UNVERIFIED','p1')"
    )

    class FakeDB:
        @contextmanager
        def connect(self):
            yield conn

    digest = native_learning_snapshot(FakeDB(), tenant_id="t1", user_id="u1")
    assert digest["form_preparation_events_checked"] == 3
    assert digest["post_scan_verified_actions"] == 3
    assert len(digest["shadow_hypotheses"]) == 1
    assert digest["native_final_submit_commands"] == 1
    assert digest["native_employer_receipts_verified"] == 1
    assert digest["native_receipts_unverified_or_blocked"] == 1
    assert "must-not-leak" not in json.dumps(digest)
    assert digest["provider_statuses_counted_as_receipts"] is False


def test_learning_snapshot_rejects_unbounded_history():
    with pytest.raises(ValueError):
        native_learning_snapshot(None, tenant_id="t1", user_id="u1", max_events=10001)
    with pytest.raises(PermissionError):
        native_learning_snapshot(None, tenant_id="", user_id="u1")


def test_native_learning_http_route_reuses_authenticated_owner_boundary():
    from fastapi.routing import APIRoute

    from munshi_apply_native import main

    route = next(
        route
        for route in main.app.routes
        if isinstance(route, APIRoute) and route.path == "/v1/native-learning/snapshot"
    )
    assert {dependency.call.__name__ for dependency in route.dependant.dependencies} == {
        "_loop_service"
    }
    assert route.methods == {"GET"}
