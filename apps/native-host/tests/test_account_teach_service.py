from __future__ import annotations

from pathlib import Path

import pytest

from munshi_apply_native.account_teach_service import AccountTeachError, AccountTeachService
from munshi_apply_native.database import Database


NOW = "2026-09-16T12:00:00+00:00"


def service(tmp_path: Path) -> tuple[Database, AccountTeachService]:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "test.sqlite", migrations)
    database.migrate()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES ('app-1', NULL, 'DETECTED', NULL, NULL, NULL, ?, ?)
            """,
            (NOW, NOW),
        )
    return database, AccountTeachService(database)


def lesson(observation: str, semantic: str, actions: list[dict[str, object]]) -> dict[str, object]:
    return {
        "observationId": observation,
        "applicationId": "app-1",
        "siteOrigin": "https://wd5.myworkdayjobs.com",
        "componentFingerprint": "cfp-account-control",
        "semanticType": semantic,
        "atsFamily": "WORKDAY",
        "tenantKey": "example",
        "uiFingerprint": "account-ui-v1",
        "actions": actions,
        "verifiedSuccess": True,
    }


def test_password_mechanics_are_learned_without_password_or_credential_reference(tmp_path: Path) -> None:
    database, teach = service(tmp_path)
    payload = lesson(
        "password-1",
        "ATS_ACCOUNT_PASSWORD_INPUT",
        [
            {"type": "FOCUS"},
            {"type": "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER"},
            {"type": "WAIT_FOR_STATE", "state": "VALUE_COMMITTED"},
        ],
    )
    captured = teach.capture(payload)
    assert captured["containsSecretMaterial"] is False
    assert teach.drain(limit=1)["learned"] == 1

    with database.connect() as connection:
        actions_json = connection.execute(
            "SELECT actions_json FROM interaction_recipes"
        ).fetchone()[0]
        lesson_json = connection.execute(
            "SELECT actions_json FROM ats_teach_lessons"
        ).fetchone()[0]
    assert "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER" in actions_json
    assert "credref:" not in actions_json
    assert "password123" not in actions_json
    assert "credref:" not in lesson_json


def test_raw_secret_value_and_credential_reference_are_rejected(tmp_path: Path) -> None:
    _, teach = service(tmp_path)
    unsafe_value = lesson(
        "unsafe-value",
        "ATS_ACCOUNT_PASSWORD_INPUT",
        [{"type": "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER", "value": "password123456"}],
    )
    with pytest.raises(AccountTeachError, match="secret/value"):
        teach.capture(unsafe_value)

    unsafe_ref = lesson(
        "unsafe-ref",
        "ATS_ACCOUNT_PASSWORD_INPUT",
        [{"type": "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER", "credentialRef": "credref:v1:abcdefghijklmnop"}],
    )
    with pytest.raises(AccountTeachError, match="secret/value"):
        teach.capture(unsafe_ref)


def test_email_code_and_link_actions_are_secretless(tmp_path: Path) -> None:
    _, teach = service(tmp_path)
    code = teach.capture(
        lesson(
            "code-1",
            "ATS_ACCOUNT_EMAIL_VERIFICATION_CODE",
            [{"type": "CONSUME_ONE_TIME_VERIFICATION_CODE"}],
        )
    )
    link = teach.capture(
        lesson(
            "link-1",
            "ATS_ACCOUNT_EMAIL_VERIFICATION_LINK",
            [{"type": "OPEN_VERIFICATION_LINK"}],
        )
    )
    assert code["queued"] is True
    assert link["queued"] is True

    raw_code = lesson(
        "code-unsafe",
        "ATS_ACCOUNT_EMAIL_VERIFICATION_CODE",
        [{"type": "CONSUME_ONE_TIME_VERIFICATION_CODE", "code": "123456"}],
    )
    with pytest.raises(AccountTeachError, match="secret/value"):
        teach.capture(raw_code)

    raw_link = lesson(
        "link-unsafe",
        "ATS_ACCOUNT_EMAIL_VERIFICATION_LINK",
        [{"type": "OPEN_VERIFICATION_LINK", "url": "https://example.test/verify?token=x"}],
    )
    with pytest.raises(AccountTeachError, match="secret/value"):
        teach.capture(raw_link)


def test_three_verified_successes_promote_and_two_verified_failures_roll_back(tmp_path: Path) -> None:
    _, teach = service(tmp_path)
    actions = [{"type": "OPEN_VERIFICATION_LINK"}]
    for index in range(1, 4):
        teach.capture(
            lesson(
                f"promote-{index}",
                "ATS_ACCOUNT_MAGIC_LOGIN",
                actions,
            )
        )
        assert teach.drain(limit=1)["learned"] == 1

    promoted = teach.lookup_promoted(
        {
            "siteOrigin": "https://wd5.myworkdayjobs.com",
            "componentFingerprint": "cfp-account-control",
            "semanticType": "ATS_ACCOUNT_MAGIC_LOGIN",
            "atsFamily": "WORKDAY",
            "tenantKey": "example",
            "uiFingerprint": "account-ui-v1",
        }
    )
    assert promoted is not None
    assert promoted["state"] == "PROMOTED"
    assert promoted["verified_successes"] == 3

    first = teach.record_verified_outcome(
        str(promoted["recipe_id"]),
        application_id="app-1",
        success=False,
        occurred_at="2026-09-16T12:01:00+00:00",
        failure_reason="verification failed",
    )
    second = teach.record_verified_outcome(
        str(promoted["recipe_id"]),
        application_id="app-1",
        success=False,
        occurred_at="2026-09-16T12:02:00+00:00",
        failure_reason="verification failed",
    )
    assert first["state"] == "PROMOTED"
    assert second["state"] == "ROLLED_BACK"
    assert second["lifecycle_state"] == "QUARANTINED"


def test_unverified_or_security_challenge_never_enters_account_teach(tmp_path: Path) -> None:
    database, teach = service(tmp_path)
    unverified = lesson(
        "not-verified",
        "ATS_ACCOUNT_PASSWORD_INPUT",
        [{"type": "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER"}],
    )
    unverified["verifiedSuccess"] = False
    with pytest.raises(AccountTeachError, match="verified"):
        teach.capture(unverified)

    with pytest.raises(AccountTeachError, match="approved"):
        teach.capture(
            lesson("totp", "TOTP", [{"type": "CLICK"}])
        )

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM ats_teach_lessons").fetchone()[0] == 0



def test_ref_only_sonnet_login_mechanics_promote_without_secret_values(
    tmp_path: Path,
) -> None:
    _, teach = service(tmp_path)
    target = "mt-" + "a" * 24
    actions = [
        {
            "type": "FILL_SECRET_REF",
            "targetRef": target,
            "secretRef": "secret:account-password",
        },
        {"type": "CLICK", "targetRef": target},
        {"type": "WAIT_FOR_STATE", "state": "AUTH_STATE_CHANGED"},
    ]
    for index in range(3):
        captured = teach.capture(
            lesson(
                f"auth-mechanics-{index}",
                "AUTH_LOGIN_MECHANICS",
                actions,
            )
        )
        assert captured["containsSecretMaterial"] is False
        assert teach.drain(limit=1)["learned"] == 1

    promoted = teach.lookup_promoted(
        {
            "siteOrigin": "https://wd5.myworkdayjobs.com",
            "componentFingerprint": "cfp-account-control",
            "semanticType": "AUTH_LOGIN_MECHANICS",
            "atsFamily": "WORKDAY",
            "tenantKey": "example",
            "uiFingerprint": "account-ui-v1",
        }
    )
    assert promoted is not None
    assert promoted["state"] == "PROMOTED"
    encoded = str(promoted["actions"])
    assert "secret:account-password" in encoded
    assert "password123" not in encoded


def test_ref_only_account_mechanics_reject_literal_secret_material(
    tmp_path: Path,
) -> None:
    _, teach = service(tmp_path)
    target = "mt-" + "b" * 24
    payload = lesson(
        "auth-literal-secret",
        "AUTH_LOGIN_MECHANICS",
        [
            {
                "type": "FILL_SECRET_REF",
                "targetRef": target,
                "secretRef": "secret:account-password",
                "value": "plaintext-password",
            }
        ],
    )
    with pytest.raises(AccountTeachError):
        teach.capture(payload)
