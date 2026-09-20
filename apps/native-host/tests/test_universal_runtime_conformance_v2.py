from __future__ import annotations

from munshi_apply_native.hosted_account_orchestrator import HostedAccountOrchestrator
from munshi_apply_native.mechanics_actions import REFERENCE_FIELDS, TARGET_ACTIONS
from munshi_apply_native.plan_browser_adapter import (
    KNOWN_PROVIDER_RECIPES,
    provider_for_url,
)


class _PolicyOnlyOrchestrator:
    plan = {
        "provider_policy": {
            "provider": "GENERIC",
            "allowed_hosts": ["jobs.example.com"],
            "mailbox_verification": {
                "mandatory": True,
                "sender_domains": ["example.com"],
                "link_hosts": ["example.com"],
            },
            "account_identity": {"username_policy": "EMAIL"},
        }
    }


def test_hosted_account_runtime_accepts_plan_bound_mailbox_policy() -> None:
    hosts, senders = HostedAccountOrchestrator._mailbox_policy(
        _PolicyOnlyOrchestrator()
    )
    assert hosts == ["example.com"]
    assert senders == ["example.com"]


def test_unknown_provider_remains_generic_and_known_workday_hints_align() -> None:
    assert provider_for_url("https://jobs.future-example.com/apply/1") == "GENERIC"
    assert provider_for_url("https://example.workdayjobs.com/job/1") == "WORKDAY"
    assert "workdayjobs.com" in KNOWN_PROVIDER_RECIPES["WORKDAY"]
    assert "myworkdaysite.com" in KNOWN_PROVIDER_RECIPES["WORKDAY"]


def test_spoofed_known_provider_host_does_not_inherit_recipe() -> None:
    assert provider_for_url("https://greenhouse.evil.test/jobs/1") == "GENERIC"
    assert provider_for_url("https://agile-ats.com.evil.test/jobs/1") == "GENERIC"


def test_runtime_mechanics_cover_private_reference_actions_without_submit() -> None:
    for action in (
        "TYPE_ANSWER_REF",
        "FILL_SECRET_REF",
        "FILL_VERIFICATION_ARTIFACT",
        "UPLOAD_ARTIFACT",
        "OPEN_LINK",
    ):
        assert action in REFERENCE_FIELDS

    for action in (
        "FOCUS",
        "CLICK",
        "NEXT",
        "TYPE_ANSWER_REF",
        "FILL_SECRET_REF",
        "FILL_VERIFICATION_ARTIFACT",
        "UPLOAD_ARTIFACT",
    ):
        assert action in TARGET_ACTIONS

    assert "FINAL_SUBMIT" not in TARGET_ACTIONS
    assert "FINAL_SUBMIT" not in REFERENCE_FIELDS
    assert "SUBMIT" not in TARGET_ACTIONS
