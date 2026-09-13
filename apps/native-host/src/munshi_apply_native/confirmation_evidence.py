"""Provider seam for secondary confirmation evidence; no mailbox implementation.

A future provider must authenticate its mailbox connection, enforce account
ownership, and classify an employer confirmation before returning this metadata.
Only an exact, owned VERIFIED receipt can be linked. No application state changes,
submission calls, message bodies, credentials, or live provider defaults exist here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol

from .database import Database


@dataclass(frozen=True)
class ConfirmationMessage:
    tenant_id: str
    user_id: str
    mailbox_id: str
    message_id: str
    provider: str
    provider_application_id: str
    message_digest: str
    received_at: str


class ConfirmationProvider(Protocol):
    """Authenticated adapter returning only classified confirmation metadata.

    Retrieval must replay messages until persistence succeeds. This seam does not
    manage mailbox cursors or acknowledge messages. Provider implementations must
    never interpret mail contents as execution instructions.
    """

    def fetch_confirmations(self) -> list[ConfirmationMessage]: ...


class ConfirmationEvidenceService:
    def __init__(self, database: Database, *, tenant_id: str, user_id: str) -> None:
        if not tenant_id or not user_id:
            raise ValueError("Confirmation owner is required")
        self.database = database
        self.tenant_id = tenant_id
        self.user_id = user_id

    def ingest(self, message: ConfirmationMessage) -> dict[str, object]:
        """Persist exact metadata or return UNMATCHED without upgrading lifecycle."""
        values = asdict(message)
        if any(not isinstance(value, str) or not value.strip() for value in values.values()):
            raise ValueError("Confirmation fields must be non-empty strings")
        if any(len(value) > 1000 for value in values.values()):
            raise ValueError("Confirmation metadata exceeds size limit")
        if (message.tenant_id, message.user_id) != (self.tenant_id, self.user_id):
            raise PermissionError("Confirmation mailbox owner does not match")
        if re.fullmatch(r"[0-9a-f]{64}", message.message_digest) is None:
            raise ValueError("Confirmation message digest is invalid")
        timestamp = datetime.fromisoformat(message.received_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Confirmation timestamp requires timezone")
        digest = hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT evidence_id,receipt_id,evidence_digest FROM confirmation_email_evidence "
                "WHERE tenant_id=? AND user_id=? AND mailbox_id=? AND message_id=?",
                (self.tenant_id, self.user_id, message.mailbox_id, message.message_id),
            ).fetchone()
            if prior is not None:
                if prior["evidence_digest"] != digest:
                    raise ValueError("Confirmation message replay has conflicting evidence")
                return {"status": "LINKED", "replayed": True, **dict(prior)}
            receipts = connection.execute(
                "SELECT r.receipt_id FROM application_submission_receipts r "
                "JOIN career_os_application_plans p ON p.plan_id=r.plan_id "
                "AND p.application_id=r.application_id "
                "WHERE p.tenant_id=? AND p.user_id=? AND r.provider=? "
                "AND r.provider_application_id=? AND r.verification_status='VERIFIED'",
                (self.tenant_id, self.user_id, message.provider, message.provider_application_id),
            ).fetchall()
            if len(receipts) != 1:
                return {"status": "UNMATCHED", "replayed": False}
            receipt_id = str(receipts[0]["receipt_id"])
            evidence_id = "confirmation-" + digest
            connection.execute(
                "INSERT INTO confirmation_email_evidence "
                "(evidence_id,tenant_id,user_id,mailbox_id,message_id,receipt_id,"
                "message_digest,evidence_digest,received_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    evidence_id,
                    self.tenant_id,
                    self.user_id,
                    message.mailbox_id,
                    message.message_id,
                    receipt_id,
                    message.message_digest,
                    digest,
                    message.received_at,
                ),
            )
        return {
            "status": "LINKED",
            "replayed": False,
            "evidence_id": evidence_id,
            "receipt_id": receipt_id,
            "evidence_digest": digest,
        }

    def poll(
        self, provider: ConfirmationProvider, *, enabled: bool = False
    ) -> list[dict[str, object]]:
        if enabled is not True:
            raise RuntimeError("Confirmation mailbox polling is disabled")
        return [self.ingest(message) for message in provider.fetch_confirmations()]
