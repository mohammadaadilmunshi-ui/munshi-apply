from __future__ import annotations

import pytest

from munshi_apply_native.mechanics_actions import (
    MechanicsActionError,
    validate_mechanics_actions,
)


def test_reference_only_mechanics_actions_are_accepted() -> None:
    target = "mt-" + "a" * 24
    actions = validate_mechanics_actions(
        [
            {"type": "CLICK", "targetRef": target},
            {
                "type": "TYPE_ANSWER_REF",
                "targetRef": target,
                "answerRef": "answer:first-name",
            },
            {
                "type": "FILL_SECRET_REF",
                "targetRef": target,
                "secretRef": "secret:account-password",
            },
            {
                "type": "FILL_VERIFICATION_ARTIFACT",
                "targetRef": target,
                "verificationRef": "verification:current",
            },
            {
                "type": "UPLOAD_ARTIFACT",
                "targetRef": target,
                "artifactRef": "artifact:resume",
            },
            {
                "type": "SELECT",
                "targetRef": target,
                "valueRef": "answer:country",
            },
            {"type": "NEXT", "targetRef": target},
            {
                "type": "WAIT_FOR_STATE",
                "state": "TARGET_VISIBLE",
                "targetRef": target,
            },
            {
                "type": "OPEN_LINK",
                "verificationRef": "verification:current",
            },
        ],
        allowed_target_refs={target},
        allowed_value_refs={
            "answer:first-name",
            "answer:country",
            "secret:account-password",
            "verification:current",
            "artifact:resume",
        },
    )
    assert actions[0] == {"type": "CLICK", "targetRef": target}
    assert actions[-1] == {
        "type": "OPEN_LINK",
        "verificationRef": "verification:current",
    }


@pytest.mark.parametrize(
    "action",
    [
        {
            "type": "FILL_SECRET_REF",
            "targetRef": "mt-" + "a" * 24,
            "secretRef": "secret:account-password",
            "value": "plaintext-password",
        },
        {
            "type": "FILL_VERIFICATION_ARTIFACT",
            "targetRef": "mt-" + "a" * 24,
            "verificationRef": "verification:current",
            "code": "482913",
        },
        {
            "type": "OPEN_LINK",
            "verificationRef": "verification:current",
            "url": "https://careers.example.com/verify/token",
        },
        {
            "type": "CLICK",
            "targetRef": "mt-" + "a" * 24,
            "selector": "#submit",
        },
    ],
)
def test_literal_secret_or_locator_material_is_rejected(
    action: dict[str, str],
) -> None:
    with pytest.raises(MechanicsActionError):
        validate_mechanics_actions([action])


def test_unobserved_target_and_unavailable_ref_are_rejected() -> None:
    observed = "mt-" + "a" * 24
    unobserved = "mt-" + "b" * 24
    with pytest.raises(MechanicsActionError):
        validate_mechanics_actions(
            [{"type": "CLICK", "targetRef": unobserved}],
            allowed_target_refs={observed},
        )
    with pytest.raises(MechanicsActionError):
        validate_mechanics_actions(
            [
                {
                    "type": "FILL_SECRET_REF",
                    "targetRef": observed,
                    "secretRef": "secret:missing",
                }
            ],
            allowed_target_refs={observed},
            allowed_value_refs={"secret:account-password"},
        )
