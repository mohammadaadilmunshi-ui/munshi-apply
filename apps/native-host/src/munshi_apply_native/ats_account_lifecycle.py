from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from .database import Database


ACCOUNT_STATES = {
    "UNPROVISIONED",
    "CREATING",
    "VERIFICATION_PENDING",
    "VERIFIED",
    "AUTHENTICATED",
    "NEEDS_USER_ACTION",
    "BLOCKED",
    "FAILED_SAFE",
}
VERIFICATION_KINDS = {
    "EMAIL_LINK",
    "EMAIL_CODE",
    "PASSWORD_RESET_LINK",
    "MAGIC_LOGIN_LINK",
}
SECURITY_INTERVENTION_KINDS = {
    "CAPTCHA",
    "SMS",
    "TOTP",
    "PASSKEY",
    "GOVERNMENT_ID",
    "BIOMETRIC",
    "LIVENESS",
    "FRAUD_CHALLENGE",
}
_SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "otp",
    "passcode",
    "magic_link",
    "reset_link",
    "verification_url",
    "verification_code",
)
_CREDENTIAL_REF_RE = re.compile(r"^credref:v1:[A-Za-z0-9_-]{16,128}$")
_HUNTER_ATS_SECRET_REF_RE = re.compile(r"^ats-secret://[A-Za-z0-9_-]{8,128}/password$")
_MAIL_ALIAS_RE = re.compile(
    r"^(?:u|a)_[A-Za-z0-9_-]{16,64}@mail\.munshi\.systems$",
    re.IGNORECASE,
)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "UNPROVISIONED": {"CREATING", "VERIFIED", "AUTHENTICATED", "FAILED_SAFE"},
    "CREATING": {
        "VERIFICATION_PENDING",
        "VERIFIED",
        "AUTHENTICATED",
        "NEEDS_USER_ACTION",
        "BLOCKED",
        "FAILED_SAFE",
    },
    "VERIFICATION_PENDING": {
        "VERIFIED",
        "AUTHENTICATED",
        "NEEDS_USER_ACTION",
        "BLOCKED",
        "FAILED_SAFE",
    },
    "VERIFIED": {"AUTHENTICATED", "VERIFICATION_PENDING", "BLOCKED", "FAILED_SAFE"},
    "AUTHENTICATED": {"VERIFICATION_PENDING", "BLOCKED", "FAILED_SAFE"},
    "NEEDS_USER_ACTION": {
        "CREATING",
        "VERIFICATION_PENDING",
        "VERIFIED",
        "AUTHENTICATED",
        "BLOCKED",
        "FAILED_SAFE",
    },
    "BLOCKED": {"CREATING", "VERIFICATION_PENDING", "VERIFIED", "FAILED_SAFE"},
    "FAILED_SAFE": {"CREATING", "VERIFICATION_PENDING", "VERIFIED", "BLOCKED"},
}


class ATSAccountLifecycleError(ValueError):
    pass


def _required(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ATSAccountLifecycleError(f"{label} must be a non-empty string")
    return value.strip()


def _timestamp(value: object, label: str) -> str:
    normalized = _required(value, label)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ATSAccountLifecycleError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ATSAccountLifecycleError(f"{label} must include a timezone")
    return normalized


def _credential_ref(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = _required(value, "credentialRef")
    if not (
        _CREDENTIAL_REF_RE.fullmatch(normalized)
        or _HUNTER_ATS_SECRET_REF_RE.fullmatch(normalized)
    ):
        raise ATSAccountLifecycleError(
            "credentialRef must be an opaque account credential reference; secret material is forbidden"
        )
    return normalized


def _mail_alias(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = _required(value, "mailAlias").lower()
    if not _MAIL_ALIAS_RE.fullmatch(normalized):
        raise ATSAccountLifecycleError(
            "mailAlias must be an opaque u_/a_ identity on mail.munshi.systems"
        )
    return normalized


def _reject_secret_material(value: object, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                raise ATSAccountLifecycleError(
                    f"Secret or one-time verification material is forbidden at {path}.{key}"
                )
            _reject_secret_material(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_material(item, f"{path}[{index}]")


def _json_metadata(value: object | None) -> str:
    if value is None:
        return "{}"
    if not isinstance(value, dict):
        raise ATSAccountLifecycleError("metadata must be an object")
    _reject_secret_material(value, "metadata")
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > 16_384:
        raise ATSAccountLifecycleError("metadata exceeds 16 KiB")
    return encoded


class ATSAccountLifecycle:
    """Durable ATS-account coordination without durable secret material.

    Passwords are referenced only by opaque ``credential_ref`` handles. One-time
    verification artifacts are never accepted by this service; callers persist
    only a digest and mail-event identity, then deliver the actual artifact over
    a one-time resolver/broker boundary.
    """

    def __init__(self, database: Database):
        self.database = database

    def _require_account(self, connection: Any, account_id: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM account_records WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise ATSAccountLifecycleError("Unknown accountId")

    def _require_application(self, connection: Any, application_id: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM applications WHERE application_id = ?",
            (application_id,),
        ).fetchone()
        if row is None:
            raise ATSAccountLifecycleError("Unknown applicationId")

    def _event(
        self,
        connection: Any,
        *,
        account_id: str,
        application_id: str | None,
        event_type: str,
        occurred_at: str,
        metadata: object | None = None,
    ) -> str:
        event_id = f"atsevt_{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO ats_account_events (
                event_id, account_id, application_id, event_type, occurred_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                account_id,
                application_id,
                event_type,
                occurred_at,
                _json_metadata(metadata),
            ),
        )
        return event_id

    def provision(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ATSAccountLifecycleError("Account lifecycle payload must be an object")
        _reject_secret_material(payload)
        account_id = _required(payload.get("accountId"), "accountId")
        provider = _required(payload.get("provider"), "provider").lower()
        observed_at = _timestamp(payload.get("observedAt"), "observedAt")
        credential_ref = _credential_ref(payload.get("credentialRef"))
        mail_alias = _mail_alias(payload.get("mailAlias"))
        with self.database.connect() as connection:
            self._require_account(connection, account_id)
            connection.execute(
                """
                INSERT INTO ats_account_state (
                    account_id, provider, credential_ref, mail_alias, state,
                    verified_at, authenticated_at, issue_code, issue_detail,
                    version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'UNPROVISIONED', NULL, NULL, NULL, NULL, 1, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    provider = excluded.provider,
                    credential_ref = COALESCE(excluded.credential_ref, ats_account_state.credential_ref),
                    mail_alias = COALESCE(excluded.mail_alias, ats_account_state.mail_alias),
                    version = ats_account_state.version + 1,
                    updated_at = excluded.updated_at
                """,
                (account_id, provider, credential_ref, mail_alias, observed_at, observed_at),
            )
        return self.snapshot(account_id)

    def transition(
        self,
        account_id: str,
        state: str,
        observed_at: str,
        *,
        issue_code: str | None = None,
        issue_detail: str | None = None,
    ) -> dict[str, object]:
        account_id = _required(account_id, "accountId")
        if state not in ACCOUNT_STATES:
            raise ATSAccountLifecycleError("Unsupported account state")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT state FROM ats_account_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if row is None:
                raise ATSAccountLifecycleError("Account lifecycle state is not provisioned")
            current = str(row[0])
            if state != current and state not in _ALLOWED_TRANSITIONS[current]:
                raise ATSAccountLifecycleError(f"Invalid account transition {current} -> {state}")
            connection.execute(
                """
                UPDATE ats_account_state
                SET state = ?, issue_code = ?, issue_detail = ?,
                    version = version + 1, updated_at = ?
                WHERE account_id = ?
                """,
                (state, issue_code, issue_detail, observed_at, account_id),
            )
        return self.snapshot(account_id)

    def begin_creation(self, account_id: str, observed_at: str) -> dict[str, object]:
        return self.transition(account_id, "CREATING", observed_at)

    def mark_created(
        self,
        account_id: str,
        application_id: str,
        observed_at: str,
        *,
        verification_required: bool,
    ) -> dict[str, object]:
        account_id = _required(account_id, "accountId")
        application_id = _required(application_id, "applicationId")
        observed_at = _timestamp(observed_at, "observedAt")
        next_state = "VERIFICATION_PENDING" if verification_required else "VERIFIED"
        with self.database.connect() as connection:
            self._require_account(connection, account_id)
            self._require_application(connection, application_id)
            row = connection.execute(
                "SELECT state FROM ats_account_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if row is None:
                raise ATSAccountLifecycleError("Account lifecycle state is not provisioned")
            current = str(row[0])
            if current != next_state and next_state not in _ALLOWED_TRANSITIONS[current]:
                raise ATSAccountLifecycleError(f"Invalid account transition {current} -> {next_state}")
            connection.execute(
                "UPDATE account_records SET exists_flag = 1, last_used = ?, updated_at = ? WHERE account_id = ?",
                (observed_at, observed_at, account_id),
            )
            connection.execute(
                """
                UPDATE ats_account_state
                SET state = ?, verified_at = CASE WHEN ? = 'VERIFIED' THEN ? ELSE verified_at END,
                    issue_code = NULL, issue_detail = NULL,
                    version = version + 1, updated_at = ?
                WHERE account_id = ?
                """,
                (next_state, next_state, observed_at, observed_at, account_id),
            )
            self._event(
                connection,
                account_id=account_id,
                application_id=application_id,
                event_type="ATS_ACCOUNT_CREATED",
                occurred_at=observed_at,
            )
            if verification_required:
                self._event(
                    connection,
                    account_id=account_id,
                    application_id=application_id,
                    event_type="ATS_ACCOUNT_VERIFICATION_PENDING",
                    occurred_at=observed_at,
                )
            else:
                self._event(
                    connection,
                    account_id=account_id,
                    application_id=application_id,
                    event_type="ATS_ACCOUNT_VERIFIED",
                    occurred_at=observed_at,
                    metadata={"verificationRequired": False},
                )
        return self.snapshot(account_id)

    def mark_verified(
        self, account_id: str, application_id: str, observed_at: str
    ) -> dict[str, object]:
        account_id = _required(account_id, "accountId")
        application_id = _required(application_id, "applicationId")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            self._require_application(connection, application_id)
            row = connection.execute(
                "SELECT state FROM ats_account_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if row is None:
                raise ATSAccountLifecycleError("Account lifecycle state is not provisioned")
            current = str(row[0])
            if current != "VERIFIED" and "VERIFIED" not in _ALLOWED_TRANSITIONS[current]:
                raise ATSAccountLifecycleError(f"Invalid account transition {current} -> VERIFIED")
            connection.execute(
                """
                UPDATE ats_account_state
                SET state = 'VERIFIED', verified_at = COALESCE(verified_at, ?),
                    issue_code = NULL, issue_detail = NULL,
                    version = version + 1, updated_at = ?
                WHERE account_id = ?
                """,
                (observed_at, observed_at, account_id),
            )
            self._event(
                connection,
                account_id=account_id,
                application_id=application_id,
                event_type="ATS_ACCOUNT_VERIFIED",
                occurred_at=observed_at,
            )
        return self.snapshot(account_id)

    def mark_authenticated(
        self, account_id: str, application_id: str, observed_at: str
    ) -> dict[str, object]:
        account_id = _required(account_id, "accountId")
        application_id = _required(application_id, "applicationId")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            self._require_application(connection, application_id)
            row = connection.execute(
                "SELECT state FROM ats_account_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if row is None:
                raise ATSAccountLifecycleError("Account lifecycle state is not provisioned")
            current = str(row[0])
            if current != "AUTHENTICATED" and "AUTHENTICATED" not in _ALLOWED_TRANSITIONS[current]:
                raise ATSAccountLifecycleError(
                    f"Invalid account transition {current} -> AUTHENTICATED"
                )
            connection.execute(
                """
                UPDATE ats_account_state
                SET state = 'AUTHENTICATED', authenticated_at = COALESCE(authenticated_at, ?),
                    issue_code = NULL, issue_detail = NULL,
                    version = version + 1, updated_at = ?
                WHERE account_id = ?
                """,
                (observed_at, observed_at, account_id),
            )
            self._event(
                connection,
                account_id=account_id,
                application_id=application_id,
                event_type="ATS_ACCOUNT_AUTHENTICATED",
                occurred_at=observed_at,
            )
        return self.snapshot(account_id)

    def bind_continuation(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ATSAccountLifecycleError("Continuation payload must be an object")
        _reject_secret_material(payload)
        continuation_id = _required(payload.get("continuationId"), "continuationId")
        account_id = _required(payload.get("accountId"), "accountId")
        application_id = _required(payload.get("applicationId"), "applicationId")
        execution_session_id = _required(
            payload.get("executionSessionId"), "executionSessionId"
        )
        provider = _required(payload.get("provider"), "provider").lower()
        target_fingerprint = _required(
            payload.get("targetFingerprint"), "targetFingerprint"
        )
        observed_at = _timestamp(payload.get("observedAt"), "observedAt")
        with self.database.connect() as connection:
            self._require_account(connection, account_id)
            self._require_application(connection, application_id)
            connection.execute(
                """
                INSERT INTO ats_account_continuations (
                    continuation_id, account_id, application_id, execution_session_id,
                    provider, target_fingerprint, state, issue_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?)
                ON CONFLICT(continuation_id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (
                    continuation_id,
                    account_id,
                    application_id,
                    execution_session_id,
                    provider,
                    target_fingerprint,
                    observed_at,
                    observed_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ats_account_continuations WHERE continuation_id = ?",
                (continuation_id,),
            ).fetchone()
        return dict(row) if row is not None else {}

    def start_verification(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ATSAccountLifecycleError("Verification payload must be an object")
        _reject_secret_material(payload)
        challenge_id = _required(payload.get("challengeId"), "challengeId")
        account_id = _required(payload.get("accountId"), "accountId")
        application_id = _required(payload.get("applicationId"), "applicationId")
        continuation_id = _required(payload.get("continuationId"), "continuationId")
        kind = _required(payload.get("kind"), "kind").upper()
        if kind not in VERIFICATION_KINDS:
            raise ATSAccountLifecycleError(
                "Only ordinary candidate-controlled email verification is automatable"
            )
        observed_at = _timestamp(payload.get("observedAt"), "observedAt")
        expires_at_value = payload.get("expiresAt")
        expires_at = (
            _timestamp(expires_at_value, "expiresAt") if expires_at_value is not None else None
        )
        with self.database.connect() as connection:
            self._require_account(connection, account_id)
            self._require_application(connection, application_id)
            continuation = connection.execute(
                """
                SELECT account_id, application_id FROM ats_account_continuations
                WHERE continuation_id = ?
                """,
                (continuation_id,),
            ).fetchone()
            if continuation is None:
                raise ATSAccountLifecycleError("Unknown continuationId")
            if str(continuation[0]) != account_id or str(continuation[1]) != application_id:
                raise ATSAccountLifecycleError("Verification continuation binding mismatch")
            connection.execute(
                """
                INSERT INTO ats_verification_challenges (
                    challenge_id, account_id, application_id, continuation_id, kind, state,
                    mail_event_id, artifact_digest, created_at, available_at, claimed_at,
                    consumed_at, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', NULL, NULL, ?, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(challenge_id) DO NOTHING
                """,
                (
                    challenge_id,
                    account_id,
                    application_id,
                    continuation_id,
                    kind,
                    observed_at,
                    expires_at,
                    observed_at,
                ),
            )
            connection.execute(
                """
                UPDATE ats_account_state
                SET state = 'VERIFICATION_PENDING', version = version + 1, updated_at = ?
                WHERE account_id = ?
                """,
                (observed_at, account_id),
            )
            row = connection.execute(
                "SELECT * FROM ats_verification_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone()
        return dict(row) if row is not None else {}

    def mark_verification_ready(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ATSAccountLifecycleError("Verification-ready payload must be an object")
        _reject_secret_material(payload)
        challenge_id = _required(payload.get("challengeId"), "challengeId")
        mail_event_id = _required(payload.get("mailEventId"), "mailEventId")
        artifact_digest = _required(payload.get("artifactDigest"), "artifactDigest").lower()
        if not _SHA256_RE.fullmatch(artifact_digest):
            raise ATSAccountLifecycleError("artifactDigest must be a lowercase SHA-256 digest")
        observed_at = _timestamp(payload.get("observedAt"), "observedAt")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ats_verification_challenges
                SET state = 'READY', mail_event_id = ?, artifact_digest = ?,
                    available_at = ?, updated_at = ?
                WHERE challenge_id = ? AND state = 'PENDING'
                """,
                (mail_event_id, artifact_digest, observed_at, observed_at, challenge_id),
            )
            if cursor.rowcount != 1:
                existing = connection.execute(
                    "SELECT * FROM ats_verification_challenges WHERE challenge_id = ?",
                    (challenge_id,),
                ).fetchone()
                if existing is None:
                    raise ATSAccountLifecycleError("Unknown challengeId")
                if str(existing["mail_event_id"] or "") != mail_event_id:
                    raise ATSAccountLifecycleError("Challenge is not pending or mail event mismatched")
            row = connection.execute(
                "SELECT * FROM ats_verification_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone()
        return dict(row) if row is not None else {}

    def claim_verification(self, challenge_id: str, observed_at: str) -> dict[str, object]:
        challenge_id = _required(challenge_id, "challengeId")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ats_verification_challenges
                SET state = 'CLAIMED', claimed_at = ?, updated_at = ?
                WHERE challenge_id = ? AND state = 'READY'
                """,
                (observed_at, observed_at, challenge_id),
            )
            row = connection.execute(
                "SELECT * FROM ats_verification_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone()
            if row is None:
                raise ATSAccountLifecycleError("Unknown challengeId")
            result = dict(row)
            result["claimedNow"] = cursor.rowcount == 1
            return result

    def requeue_claim(self, challenge_id: str, observed_at: str) -> dict[str, object]:
        """Re-open a claimed challenge after restart if its mail event is re-resolvable.

        This does not restore or persist the one-time artifact itself. The caller
        must fetch the artifact again from the trusted mail resolver and validate
        it against ``artifact_digest`` before use.
        """
        challenge_id = _required(challenge_id, "challengeId")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE ats_verification_challenges
                SET state = 'READY', claimed_at = NULL, updated_at = ?
                WHERE challenge_id = ? AND state = 'CLAIMED' AND mail_event_id IS NOT NULL
                """,
                (observed_at, challenge_id),
            )
            row = connection.execute(
                "SELECT * FROM ats_verification_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone()
        if row is None:
            raise ATSAccountLifecycleError("Unknown challengeId")
        return dict(row)

    def consume_verification(self, challenge_id: str, observed_at: str) -> dict[str, object]:
        challenge_id = _required(challenge_id, "challengeId")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ats_verification_challenges
                SET state = 'CONSUMED', consumed_at = ?, updated_at = ?
                WHERE challenge_id = ? AND state = 'CLAIMED'
                """,
                (observed_at, observed_at, challenge_id),
            )
            if cursor.rowcount != 1:
                raise ATSAccountLifecycleError("Verification artifact is not exclusively claimed")
            row = connection.execute(
                "SELECT * FROM ats_verification_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone()
        return dict(row) if row is not None else {}

    def mark_continuation_ready(
        self, continuation_id: str, observed_at: str
    ) -> dict[str, object]:
        continuation_id = _required(continuation_id, "continuationId")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ats_account_continuations
                SET state = 'READY', issue_code = NULL, updated_at = ?
                WHERE continuation_id = ? AND state = 'PENDING'
                """,
                (observed_at, continuation_id),
            )
            row = connection.execute(
                "SELECT * FROM ats_account_continuations WHERE continuation_id = ?",
                (continuation_id,),
            ).fetchone()
            if row is None:
                raise ATSAccountLifecycleError("Unknown continuationId")
            if cursor.rowcount != 1 and str(row["state"]) != "READY":
                raise ATSAccountLifecycleError("Continuation cannot become READY from its current state")
        return dict(row)

    def consume_continuation(
        self, continuation_id: str, observed_at: str
    ) -> dict[str, object]:
        continuation_id = _required(continuation_id, "continuationId")
        observed_at = _timestamp(observed_at, "observedAt")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ats_account_continuations
                SET state = 'CONSUMED', updated_at = ?
                WHERE continuation_id = ? AND state = 'READY'
                """,
                (observed_at, continuation_id),
            )
            if cursor.rowcount != 1:
                raise ATSAccountLifecycleError("Continuation is not exclusively READY")
            row = connection.execute(
                "SELECT * FROM ats_account_continuations WHERE continuation_id = ?",
                (continuation_id,),
            ).fetchone()
        return dict(row) if row is not None else {}

    def security_issue(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ATSAccountLifecycleError("Security issue payload must be an object")
        _reject_secret_material(payload)
        account_id = _required(payload.get("accountId"), "accountId")
        application_id = _required(payload.get("applicationId"), "applicationId")
        challenge_kind = _required(payload.get("challengeKind"), "challengeKind").upper()
        if challenge_kind not in SECURITY_INTERVENTION_KINDS:
            raise ATSAccountLifecycleError("challengeKind is not a protected security intervention")
        observed_at = _timestamp(payload.get("observedAt"), "observedAt")
        continuation_id = payload.get("continuationId")
        normalized_continuation = (
            _required(continuation_id, "continuationId") if continuation_id is not None else None
        )
        with self.database.connect() as connection:
            self._require_application(connection, application_id)
            connection.execute(
                """
                UPDATE ats_account_state
                SET state = 'NEEDS_USER_ACTION', issue_code = ?, issue_detail = ?,
                    version = version + 1, updated_at = ?
                WHERE account_id = ?
                """,
                (
                    f"SECURITY_INTERVENTION_{challenge_kind}",
                    "External security intervention is required; state was preserved",
                    observed_at,
                    account_id,
                ),
            )
            if normalized_continuation is not None:
                connection.execute(
                    """
                    UPDATE ats_account_continuations
                    SET state = 'ISSUE', issue_code = ?, updated_at = ?
                    WHERE continuation_id = ? AND account_id = ? AND application_id = ?
                    """,
                    (
                        f"SECURITY_INTERVENTION_{challenge_kind}",
                        observed_at,
                        normalized_continuation,
                        account_id,
                        application_id,
                    ),
                )
            self._event(
                connection,
                account_id=account_id,
                application_id=application_id,
                event_type="ATS_ACCOUNT_ISSUE",
                occurred_at=observed_at,
                metadata={"challengeKind": challenge_kind},
            )
        return self.snapshot(account_id)

    def snapshot(self, account_id: str) -> dict[str, object]:
        account_id = _required(account_id, "accountId")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ats_account_state WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if row is None:
                raise ATSAccountLifecycleError("Account lifecycle state is not provisioned")
            continuations = connection.execute(
                """
                SELECT * FROM ats_account_continuations
                WHERE account_id = ? ORDER BY created_at, continuation_id
                """,
                (account_id,),
            ).fetchall()
            challenges = connection.execute(
                """
                SELECT * FROM ats_verification_challenges
                WHERE account_id = ? ORDER BY created_at, challenge_id
                """,
                (account_id,),
            ).fetchall()
            events = connection.execute(
                """
                SELECT event_id, account_id, application_id, event_type, occurred_at, metadata_json
                FROM ats_account_events
                WHERE account_id = ? ORDER BY occurred_at, event_id
                """,
                (account_id,),
            ).fetchall()
        state = dict(row)
        state["continuations"] = [dict(item) for item in continuations]
        state["verificationChallenges"] = [dict(item) for item in challenges]
        state["events"] = [
            {
                **{key: item[key] for key in item.keys() if key != "metadata_json"},
                "metadata": json.loads(str(item["metadata_json"])),
            }
            for item in events
        ]
        return state
