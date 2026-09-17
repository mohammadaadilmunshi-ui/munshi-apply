from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from .database import Database

_SHARED_TENANT_HOSTS = (
    "myworkdayjobs.com",
    "myworkdaysite.com",
    "myworkday.com",
)
_SECRET_KEY_PARTS = ("password", "secret", "token", "credential", "passcode", "otp")


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label)


def _reject_secret_material(value: object, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower().replace("_", "").replace("-", "")
            if any(part in normalized_key for part in _SECRET_KEY_PARTS):
                raise ValueError(
                    "Account registry refuses passwords, tokens, credentials, "
                    "OTPs, and other secrets"
                )
            _reject_secret_material(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secret_material(nested, f"{path}[{index}]")


def portal_identity(raw_url: object) -> tuple[str, str, str]:
    portal_url = _required_text(raw_url, "portalUrl")
    parsed = urlparse(portal_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("portalUrl must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("portalUrl must not contain embedded credentials")

    domain = parsed.hostname.lower()
    sanitized_url = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            "",
            "",
        )
    )
    shared = any(
        domain == suffix or domain.endswith(f".{suffix}")
        for suffix in _SHARED_TENANT_HOSTS
    )
    if not shared:
        return domain, domain, sanitized_url

    tenant = next(
        (
            segment.strip().lower()
            for segment in parsed.path.split("/")
            if segment.strip()
        ),
        None,
    )
    scope_key = f"{domain}/{tenant}" if tenant else domain
    return domain, scope_key, sanitized_url


class AccountStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _record(self, connection: Any, row: Any) -> dict[str, object]:
        application_ids = [
            item["application_id"]
            for item in connection.execute(
                """
                SELECT application_id
                FROM account_application_links
                WHERE account_id = ?
                ORDER BY linked_at, application_id
                """,
                (row["account_id"],),
            ).fetchall()
        ]
        return {
            "accountId": row["account_id"],
            "employer": row["employer"],
            "domain": row["domain"],
            "scopeKey": row["scope_key"],
            "portalUrl": row["portal_url"],
            "email": row["email"],
            "exists": bool(row["exists_flag"]),
            "createdAt": row["created_at"],
            "lastUsed": row["last_used"],
            "applicationIds": application_ids,
        }

    def lookup(self, payload: object) -> list[dict[str, object]]:
        if not isinstance(payload, dict):
            raise ValueError("Account lookup payload must be an object")
        _reject_secret_material(payload)
        _, scope_key, _ = portal_identity(payload.get("portalUrl"))
        email_value = payload.get("email")
        email = (
            _required_text(email_value, "email").lower()
            if email_value is not None
            else None
        )

        with self.database.connect() as connection:
            if email:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM account_records
                    WHERE scope_key = ? AND email = ?
                    ORDER BY last_used DESC, account_id
                    """,
                    (scope_key, email),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM account_records
                    WHERE scope_key = ?
                    ORDER BY last_used DESC, account_id
                    """,
                    (scope_key,),
                ).fetchall()
            return [self._record(connection, row) for row in rows]

    def upsert(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("Account upsert payload must be an object")
        _reject_secret_material(payload)

        domain, scope_key, portal_url = portal_identity(payload.get("portalUrl"))
        email = _required_text(payload.get("email"), "email").lower()
        employer = _optional_text(payload.get("employer"), "employer")
        observed_at = _required_text(payload.get("observedAt"), "observedAt")
        account_id = _required_text(
            payload.get("accountId") or f"account-{scope_key}-{email}", "accountId"
        )
        exists = payload.get("exists", True)
        if not isinstance(exists, bool):
            raise ValueError("exists must be boolean")
        application_id = _optional_text(payload.get("applicationId"), "applicationId")

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO account_records (
                    account_id, employer, scope_key, domain, portal_url, email,
                    exists_flag, created_at, last_used, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_key, email) DO UPDATE SET
                    employer = COALESCE(excluded.employer, account_records.employer),
                    domain = excluded.domain,
                    portal_url = excluded.portal_url,
                    exists_flag = excluded.exists_flag,
                    last_used = excluded.last_used,
                    updated_at = excluded.updated_at
                """,
                (
                    account_id,
                    employer,
                    scope_key,
                    domain,
                    portal_url,
                    email,
                    int(exists),
                    observed_at,
                    observed_at,
                    observed_at,
                ),
            )
            row = connection.execute(
                """
                SELECT *
                FROM account_records
                WHERE scope_key = ? AND email = ?
                """,
                (scope_key, email),
            ).fetchone()
            if row is None:
                raise RuntimeError("Account registry write was not persisted")
            if application_id:
                connection.execute(
                    """
                    INSERT INTO account_application_links (
                        account_id, application_id, linked_at
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(account_id, application_id) DO NOTHING
                    """,
                    (row["account_id"], application_id, observed_at),
                )
            return self._record(connection, row)
