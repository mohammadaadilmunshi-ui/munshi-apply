"""Encrypted persistence for hosted Chromium ATS account sessions."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .database import Database

_ALGORITHM = "aes-gcm-v1"


class HostedAccountSessionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _key(secret: bytes, *, tenant_id: str, user_id: str, scope_key: str) -> bytes:
    if len(secret) < 16:
        raise HostedAccountSessionError("Hosted account session key is unavailable")
    return hmac.new(
        secret,
        f"hosted-account-session:{tenant_id}:{user_id}:{scope_key}".encode(),
        hashlib.sha256,
    ).digest()


def _aad(*, tenant_id: str, user_id: str, scope_key: str, account_id: str | None) -> bytes:
    return json.dumps(
        {
            "v": 1,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "scope_key": scope_key,
            "account_id": account_id,
            "algorithm": _ALGORITHM,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


class HostedAccountSessionStore:
    def __init__(self, database: Database, *, bridge_secret: bytes) -> None:
        self.database = database
        self.bridge_secret = bytes(bridge_secret)

    def load(
        self,
        *,
        tenant_id: str,
        user_id: str,
        scope_key: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM hosted_account_sessions
                WHERE tenant_id=? AND user_id=? AND scope_key=?
                """,
                (tenant_id, user_id, scope_key),
            ).fetchone()
        if row is None:
            return None
        if str(row["algorithm"]) != _ALGORITHM:
            raise HostedAccountSessionError("Hosted account session algorithm is unsupported")
        try:
            plaintext = AESGCM(
                _key(
                    self.bridge_secret,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    scope_key=scope_key,
                )
            ).decrypt(
                bytes(row["nonce"]),
                bytes(row["ciphertext"]),
                _aad(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    scope_key=scope_key,
                    account_id=str(row["account_id"]) if row["account_id"] else None,
                ),
            )
            if hashlib.sha256(plaintext).hexdigest() != str(row["state_sha256"]):
                raise HostedAccountSessionError("Hosted account session digest mismatch")
            decoded = json.loads(plaintext)
        except HostedAccountSessionError:
            raise
        except Exception as error:
            raise HostedAccountSessionError(
                "Hosted account session could not be decrypted"
            ) from error
        if not isinstance(decoded, dict):
            raise HostedAccountSessionError("Hosted account session payload is invalid")
        return decoded

    def save(
        self,
        *,
        tenant_id: str,
        user_id: str,
        scope_key: str,
        account_id: str | None,
        storage_state: dict[str, Any],
    ) -> None:
        if not isinstance(storage_state, dict):
            raise HostedAccountSessionError("Chromium storage state must be an object")
        plaintext = json.dumps(
            storage_state,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        if len(plaintext) > 4 * 1024 * 1024:
            raise HostedAccountSessionError("Chromium storage state exceeds 4 MiB")
        nonce = os.urandom(12)
        ciphertext = AESGCM(
            _key(
                self.bridge_secret,
                tenant_id=tenant_id,
                user_id=user_id,
                scope_key=scope_key,
            )
        ).encrypt(
            nonce,
            plaintext,
            _aad(
                tenant_id=tenant_id,
                user_id=user_id,
                scope_key=scope_key,
                account_id=account_id,
            ),
        )
        now = _now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO hosted_account_sessions(
                  tenant_id,user_id,scope_key,account_id,ciphertext,nonce,
                  algorithm,state_sha256,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,user_id,scope_key) DO UPDATE SET
                  account_id=excluded.account_id,
                  ciphertext=excluded.ciphertext,
                  nonce=excluded.nonce,
                  algorithm=excluded.algorithm,
                  state_sha256=excluded.state_sha256,
                  updated_at=excluded.updated_at
                """,
                (
                    tenant_id,
                    user_id,
                    scope_key,
                    account_id,
                    ciphertext,
                    nonce,
                    _ALGORITHM,
                    hashlib.sha256(plaintext).hexdigest(),
                    now,
                    now,
                ),
            )

    def delete(self, *, tenant_id: str, user_id: str, scope_key: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                DELETE FROM hosted_account_sessions
                WHERE tenant_id=? AND user_id=? AND scope_key=?
                """,
                (tenant_id, user_id, scope_key),
            )
