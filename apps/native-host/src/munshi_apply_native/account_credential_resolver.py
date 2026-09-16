from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


_CREDENTIAL_REF_RE = re.compile(r"^credref:v1:[A-Za-z0-9_-]{16,128}$")


class AccountCredentialResolverError(RuntimeError):
    pass


class AccountCredentialResolver(Protocol):
    """Privileged boundary for ATS account secrets.

    Recipes, lifecycle records, browser plans, and Teach MUNSHI carry only the
    opaque reference. The resolved secret exists only for the immediate browser
    operation and must never be returned in telemetry or persisted state.
    """

    def resolve_password(self, credential_ref: str) -> str:
        ...


def validate_credential_ref(value: object) -> str:
    if not isinstance(value, str) or not _CREDENTIAL_REF_RE.fullmatch(value.strip()):
        raise AccountCredentialResolverError("Invalid opaque ATS credential reference")
    return value.strip()


@dataclass
class ResolverBackedPasswordAction:
    credential_ref: str
    control_id: str

    @classmethod
    def from_payload(cls, payload: object) -> "ResolverBackedPasswordAction":
        if not isinstance(payload, dict):
            raise AccountCredentialResolverError("Password action payload must be an object")
        allowed = {"credentialRef", "controlId"}
        unexpected = set(payload) - allowed
        if unexpected:
            raise AccountCredentialResolverError(
                "Password action may contain only credentialRef and controlId"
            )
        control_id = payload.get("controlId")
        if not isinstance(control_id, str) or not control_id.strip():
            raise AccountCredentialResolverError("Password action controlId is required")
        return cls(
            credential_ref=validate_credential_ref(payload.get("credentialRef")),
            control_id=control_id.strip(),
        )

    def resolve_for_immediate_use(self, resolver: AccountCredentialResolver) -> str:
        secret = resolver.resolve_password(self.credential_ref)
        if not isinstance(secret, str) or len(secret) < 12:
            raise AccountCredentialResolverError("Credential resolver returned an unusable password")
        return secret


class InMemoryAccountCredentialResolver:
    """Synthetic-test resolver only; never used as a production vault."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values or {})
        self.resolve_calls: list[str] = []

    def resolve_password(self, credential_ref: str) -> str:
        normalized = validate_credential_ref(credential_ref)
        self.resolve_calls.append(normalized)
        value = self._values.get(normalized)
        if value is None:
            raise AccountCredentialResolverError("Credential reference is unavailable")
        return value
