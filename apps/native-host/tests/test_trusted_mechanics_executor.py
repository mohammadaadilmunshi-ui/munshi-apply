from __future__ import annotations

import pytest

from munshi_apply_native.trusted_mechanics_executor import (
    TrustedMechanicsError,
    TrustedMechanicsExecutor,
)


class _Locator:
    def __init__(self) -> None:
        self.filled: list[str] = []
        self.clicked = 0
        self.files: list[dict[str, object]] = []
        self.keys: list[str] = []

    def fill(self, value: str) -> None:
        self.filled.append(value)

    def click(self) -> None:
        self.clicked += 1

    def set_input_files(self, payload: dict[str, object]) -> None:
        self.files.append(payload)

    def press(self, key: str) -> None:
        self.keys.append(key)

    def focus(self) -> None:
        return None


class _Page:
    url = "https://careers.example.com/apply"

    def __init__(self) -> None:
        self.visited: list[str] = []

    def goto(self, url: str, **_kwargs: object) -> None:
        self.visited.append(url)
        self.url = url


def _target_ref(char: str) -> str:
    return "mt-" + char * 24


def test_secret_verification_and_file_values_resolve_only_in_executor() -> None:
    page = _Page()
    password = "-".join(("local", "managed", "password", "value"))
    code = "482913"
    resume = {
        "name": "resume.pdf",
        "mimeType": "application/pdf",
        "buffer": b"resume-bytes",
    }
    secret_calls: list[str] = []
    verification_calls: list[str] = []
    artifact_calls: list[str] = []
    target = _target_ref("a")
    locator = _Locator()

    executor = TrustedMechanicsExecutor(
        page,
        secret_resolver=lambda ref: secret_calls.append(ref) or password,
        verification_resolver=lambda ref: (
            verification_calls.append(ref)
            or {"kind": "EMAIL_VERIFICATION_CODE", "value": code}
        ),
        artifact_resolver=lambda ref: artifact_calls.append(ref) or resume,
    )
    executor._targets[target] = (  # noqa: SLF001 - trusted-executor contract fixture
        locator,
        {
            "fileInput": True,
            "finalSubmitRisk": False,
            "type": "file",
        },
    )

    executor.execute(
        [
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
        ],
        allowed_value_refs={
            "secret:account-password",
            "verification:current",
            "artifact:resume",
        },
    )

    assert secret_calls == ["secret:account-password"]
    assert verification_calls == ["verification:current"]
    assert artifact_calls == ["artifact:resume"]
    assert locator.filled == [password, code]
    assert locator.files == [resume]


def test_open_link_resolves_verification_url_locally_and_checks_host() -> None:
    page = _Page()
    link = "https://verify.careers.example.com/email/token"
    executor = TrustedMechanicsExecutor(
        page,
        verification_resolver=lambda _ref: {
            "kind": "EMAIL_VERIFICATION_LINK",
            "value": link,
        },
        allowed_open_hosts={"careers.example.com"},
    )

    executor.execute(
        [{"type": "OPEN_LINK", "verificationRef": "verification:current"}],
        allowed_value_refs={"verification:current"},
    )

    assert page.visited == [link]


def test_application_submit_controls_remain_outside_sonnet_authority() -> None:
    page = _Page()
    target = _target_ref("b")
    locator = _Locator()
    executor = TrustedMechanicsExecutor(page)
    executor._targets[target] = (  # noqa: SLF001 - safety-boundary fixture
        locator,
        {
            "fileInput": False,
            "finalSubmitRisk": True,
            "type": "submit",
            "label": "Submit application",
        },
    )

    with pytest.raises(TrustedMechanicsError):
        executor.execute(
            [{"type": "CLICK", "targetRef": target}],
            allowed_value_refs=set(),
        )
    assert locator.clicked == 0


def test_submit_type_click_is_allowed_only_inside_explicit_auth_boundary() -> None:
    page = _Page()
    target = _target_ref("c")
    meta = {
        "fileInput": False,
        "finalSubmitRisk": False,
        "type": "submit",
        "label": "Sign in",
    }

    ordinary = TrustedMechanicsExecutor(page)
    ordinary_locator = _Locator()
    ordinary._targets[target] = (ordinary_locator, meta)  # noqa: SLF001
    with pytest.raises(TrustedMechanicsError):
        ordinary.execute(
            [{"type": "CLICK", "targetRef": target}],
            allowed_value_refs=set(),
        )

    auth = TrustedMechanicsExecutor(page, allow_submit_controls=True)
    auth_locator = _Locator()
    auth._targets[target] = (auth_locator, meta)  # noqa: SLF001
    auth.execute(
        [{"type": "CLICK", "targetRef": target}],
        allowed_value_refs=set(),
    )
    assert auth_locator.clicked == 1
