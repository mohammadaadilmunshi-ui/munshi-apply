"""Default-off, inert consumer for Hunter-issued canonical submit authorization.

This module is the production counterpart of ``synthetic_submit_command_inbox``.
It accepts, durably claims, and (via ``consume_for_execution``) returns a
single one-use proof that ``CompleteApplicationLoopService.submit`` must
present to cross the irreversible employer-submit boundary.

Design contract (mirrors ``synthetic_submit_command_inbox.py``):

* Pydantic envelope validation with ``extra="forbid"``.
* Transport-style integrity (re-serialise canonically and byte-compare).
* Local binding validation against durable Apply rows (plan, session,
  checkpoint) — never against Hunter-internal digest builders.
* Durable, state-guarded claim transitions; one-use local execution record.

Importantly: this module NEVER recomputes Hunter-internal digests
(``review_digest``, ``prepared_package_digest``, ``approval_digest``). Apply is
the execution authority, not the digest authority — Hunter's atomic CLAIM is
the single source of truth for those digests. Recomputing them here would
introduce a third divergent digest builder and undermine the loop closure.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from .database import Database

ENVELOPE_VERSION = "munshi-submit-authorization-v1"
PRODUCTION_AUTHORITY_ENV = "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED"
APPROVED_REVIEW_VERSION = "munshi-application-review-v2"

# Claim state machine values used in production_submit_authority_claims.state.
CLAIM_STATE_RECEIVED = "RECEIVED"
CLAIM_STATE_IN_FLIGHT = "CLAIM_IN_FLIGHT"
CLAIM_STATE_CLAIMED = "CLAIMED"
CLAIM_STATE_REJECTED = "REJECTED"
CLAIM_STATE_AMBIGUOUS = "AMBIGUOUS"

_CLAIM_STATES = frozenset(
    {
        CLAIM_STATE_RECEIVED,
        CLAIM_STATE_IN_FLIGHT,
        CLAIM_STATE_CLAIMED,
        CLAIM_STATE_REJECTED,
        CLAIM_STATE_AMBIGUOUS,
    }
)


def production_authority_enabled() -> bool:
    return str(os.getenv(PRODUCTION_AUTHORITY_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _canonical_envelope(value: dict[str, Any]) -> bytes:
    """Match Hunter application_submit_authority_v1._canonical exactly."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def expected_claim_digest(
    *,
    authorization_id: str,
    authority_digest: str,
    claimant_id: str,
    generation: int,
) -> str:
    """Reproduce Hunter's deterministic claim receipt.

    Mirrors ``application_submit_authorization_v1._claim_receipt`` exactly:
    ``sha256(canonical({authorization_id, authority_digest, claimant_id,
    generation}))``. The driver needs this to recognise the receipt Hunter
    returns for the claimant identity it committed to.
    """
    return hashlib.sha256(
        _canonical_envelope(
            {
                "authorization_id": authorization_id,
                "authority_digest": authority_digest,
                "claimant_id": claimant_id,
                "generation": int(generation),
            }
        )
    ).hexdigest()


def _digest(value: Any, label: str) -> str:
    normalized = str(value or "").strip().casefold()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def _text(value: Any, label: str, maximum: int = 4000) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} is required and must be at most {maximum} characters")
    return normalized


class SubmitAuthorityEnvelope(BaseModel):
    """Canonical Hunter-issued production submit authority envelope.

    This is a *parser*, not a digest builder. Apply never recomputes
    ``review_digest``/``prepared_package_digest``/``approval_digest``; those
    digests are minted by Hunter and verified by Hunter's atomic CLAIM.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["munshi-submit-authorization-v1"]
    authorization_id: str = Field(min_length=1, max_length=240)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    application_id: str = Field(min_length=1, max_length=240)
    plan_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=240)
    review_id: str = Field(min_length=1, max_length=240)
    approval_id: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=64)
    target_url: str = Field(min_length=1, max_length=4000)
    checkpoint_id: str = Field(min_length=1, max_length=240)
    generation: int = Field(strict=True, gt=0)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prepared_package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    browser_form_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    resume_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cover_letter_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    issued_at: str
    expires_at: str
    synthetic: Literal[False]
    submission_authority: Literal[True]
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: str = Field(pattern=r"^sha256=[0-9a-f]{64}$")

    @field_validator(
        "authorization_id",
        "tenant_id",
        "user_id",
        "application_id",
        "plan_id",
        "session_id",
        "review_id",
        "approval_id",
        "provider",
        "checkpoint_id",
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("submit authority identifiers cannot be blank")
        return normalized

    @field_validator("provider")
    @classmethod
    def provider_upper(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("submit authority provider is required")
        return normalized

    @field_validator("target_url")
    @classmethod
    def target_https(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.lower().startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ValueError("submit authority target must use HTTPS (or loopback for local)")
        return normalized

    @field_validator("issued_at", "expires_at")
    @classmethod
    def iso8601(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("issued_at/expires_at must be non-empty ISO-8601 strings")
        # We deliberately don't parse/datetime-validate here; the caller passes
        # the same string Hunter minted, and we only compare ordering.
        return normalized

    @field_validator("signature")
    @classmethod
    def signature_hex(cls, value: str) -> str:
        if not value.startswith("sha256="):
            raise ValueError("submit authority signature must be sha256=<hex>")
        return value


@dataclass(frozen=True)
class SubmitAuthorityAcceptResult:
    accepted: bool
    replayed: bool
    authorization_id: str | None = None
    state: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SubmitAuthorityClaimProof:
    """Result of ``consume_for_execution``.

    ``claimant_id`` is the stable identity Apply committed to when it moved the
    claim in-flight. The driver must present that exact value to Hunter's
    ``SUBMIT_AUTHORIZATION_CLAIM``; Hunter's receipt is deterministic in it, so
    exposing it here is what lets a lost response converge instead of stranding
    a consumed approval.
    """

    claimed: bool
    authorization_id: str | None
    authority_digest: str | None
    claim_digest: str | None
    generation: int | None
    state: str | None
    error: str | None = None
    claimant_id: str | None = None


class SubmitAuthorityInbox:
    """Production canonical-authority inbox (one durable receipt per envelope).

    The inbox stores Hunter-issued authorities durably, enforces a claim state
    machine that prevents blind re-submission on a lost response, and gates
    local execution behind exactly one ``consume_for_execution`` per authority.
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        # Deliberately keyless. Hunter signs the envelope with
        # MUNSHI_PRODUCTION_SUBMIT_AUTH_HMAC_SECRET, which Apply must never hold:
        # that key is the sole minting root, so possessing it would let Apply
        # author a submission with no customer approval. Apply therefore checks
        # unkeyed integrity plus its own durable bindings, and treats Hunter's
        # atomic one-use claim as the only thing that can attest authority.

    # ------------------------------------------------------------------
    # Transport parsing (structural integrity + canonical body byte-compare)
    # ------------------------------------------------------------------

    def _expected_authority_digest(
        self, envelope: SubmitAuthorityEnvelope
    ) -> str:
        """Recompute Hunter's ``authority_digest`` from the 24-key MATERIAL.

        Hunter signs: ``authority_digest = sha256(canonical(material))`` where
        ``material`` is the 24-field envelope WITHOUT ``authority_digest`` and
        ``signature``. This recompute is an unkeyed integrity check: it proves
        the envelope was not mutated in transit and is internally consistent.
        It is not authority -- authority is granted only by Hunter's atomic
        one-use claim (``SUBMIT_AUTHORIZATION_CLAIM``).
        """
        material = envelope.model_dump(mode="json")
        # Strip the two signature-bearing fields Hunter does not include in
        # the canonical material it hashes.
        material.pop("signature", None)
        material.pop("authority_digest", None)
        return hashlib.sha256(_canonical_envelope(material)).hexdigest()

    def _parse_transport(
        self,
        body: bytes,
        *,
        body_sha256: str,
        signature: str,
    ) -> tuple[SubmitAuthorityEnvelope, str, str]:
        digest = hashlib.sha256(body).hexdigest()
        supplied_digest = _digest(body_sha256, "Submit authority body digest")
        if not hmac.compare_digest(digest, supplied_digest):
            raise ValueError("submit authority body digest mismatch")

        normalized_signature = str(signature or "").strip()
        if normalized_signature.casefold().startswith("sha256="):
            normalized_signature = normalized_signature.split("=", 1)[1]
        normalized_signature = _digest(normalized_signature, "Submit authority signature")

        try:
            payload = json.loads(body)
            envelope = SubmitAuthorityEnvelope.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as error:
            raise ValueError("malformed submit authority envelope") from error

        # Unkeyed integrity only: the digest must match the material exactly.
        expected_auth_digest = self._expected_authority_digest(envelope)
        if not hmac.compare_digest(expected_auth_digest, envelope.authority_digest):
            raise ValueError("submit authority digest does not match material")

        # Byte-equality check guards against any in-flight mutation of the
        # envelope (e.g. field reordering or whitespace reformatting).
        canonical = _canonical_envelope(envelope.model_dump(mode="json"))
        if not hmac.compare_digest(canonical, body):
            raise ValueError("submit authority body is not canonical Hunter JSON")

        return envelope, digest, normalized_signature

    @staticmethod
    def _assert_fresh(envelope: SubmitAuthorityEnvelope, *, now: str) -> None:
        """``now`` is an ISO-8601 string.

        Hunter may emit ``+00:00`` or ``Z`` for the same instant. We
        normalize both forms to ``+00:00`` before ordering so lexicographic
        comparison is meaningful.
        """
        if not isinstance(now, str) or not now.strip():
            raise ValueError("Submit authority current time must be an ISO-8601 string")

        def _normalize(value: str) -> str:
            return value[:-1] + "+00:00" if value.endswith("Z") else value

        issued = _normalize(envelope.issued_at)
        expires = _normalize(envelope.expires_at)
        current = _normalize(now)
        if not (issued <= current <= expires):
            raise ValueError("expired or not-yet-issued submit authority")

    # ------------------------------------------------------------------
    # Local binding validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_bindings_locked(
        connection: sqlite3.Connection,
        envelope: SubmitAuthorityEnvelope,
    ) -> None:
        """Bind the authority to Apply's OWN durable state.

        This intentionally does NOT recompute Hunter's internal digests
        (``review_digest``, ``prepared_package_digest``, ``approval_digest``):
        those are Hunter's atomic claim assertion. Apply is the execution
        authority, not the digest authority; recomputing them here would
        introduce a third divergent digest builder and undermine the loop
        closure.
        """
        plan_row = connection.execute(
            """SELECT * FROM career_os_application_plans
               WHERE plan_id=? AND tenant_id=? AND user_id=?""",
            (envelope.plan_id, envelope.tenant_id, envelope.user_id),
        ).fetchone()
        session = connection.execute(
            """SELECT * FROM complete_application_sessions
               WHERE session_id=? AND application_id=? AND plan_id=?""",
            (envelope.session_id, envelope.application_id, envelope.plan_id),
        ).fetchone()
        application = connection.execute(
            "SELECT * FROM applications WHERE application_id=?",
            (envelope.application_id,),
        ).fetchone()
        if plan_row is None or session is None or application is None:
            raise ValueError("owned plan, application, or session is unavailable")

        if str(plan_row["acceptance_state"]) != "PLAN_ACCEPTED":
            raise ValueError("Application Plan is not accepted")
        if str(plan_row["application_id"]) != envelope.application_id:
            raise ValueError("Application Plan application binding changed")
        if str(plan_row["provider"]).upper() != envelope.provider.upper():
            raise ValueError("Application Plan provider binding changed")
        if str(plan_row["plan_digest"]) != envelope.plan_digest:
            raise ValueError("Application Plan digest binding changed")

        if str(session["provider"]).upper() != envelope.provider.upper():
            raise ValueError("execution session provider changed")
        if str(session["state"]) != "READY_TO_SUBMIT":
            raise ValueError("execution session is not READY_TO_SUBMIT")
        if str(application["status"]) != "READY_TO_SUBMIT":
            raise ValueError("application is not READY_TO_SUBMIT")
        if str(session["current_url"] or "") != envelope.target_url:
            raise ValueError("execution session destination changed")
        if str(session["browser_form_digest"] or "") != envelope.browser_form_digest:
            raise ValueError("execution session browser form changed")
        if str(session["checkpoint_id"] or "") != envelope.checkpoint_id:
            raise ValueError("execution session checkpoint changed")

        # Validate cover-letter binding against the plan payload. Hunter's
        # atomic CLAIM does NOT recompute cover-letter identity; Apply is the
        # authority on what its plan accepted. If the plan has a cover
        # letter, the envelope's cover_letter_sha256 must equal the plan's
        # digest; if the plan has none, the envelope must carry None.
        try:
            plan = json.loads(str(plan_row["plan_json"]))
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("stored Application Plan is malformed") from error
        if not isinstance(plan, dict):
            raise ValueError("stored Application Plan is malformed")
        cover = plan.get("cover_letter")
        if isinstance(cover, dict):
            expected_cover = str(cover.get("artifact_sha256") or "").lower()
            if envelope.cover_letter_sha256 is None or (
                str(envelope.cover_letter_sha256).lower() != expected_cover
            ):
                raise ValueError("cover-letter digest does not match Application Plan")
        elif envelope.cover_letter_sha256 is not None:
            raise ValueError("submit authority contains unexpected cover-letter digest")

        checkpoint = connection.execute(
            """SELECT * FROM application_checkpoints
               WHERE checkpoint_id=? AND application_id=?""",
            (envelope.checkpoint_id, envelope.application_id),
        ).fetchone()
        if checkpoint is None:
            raise ValueError("execution checkpoint is unavailable")
        if str(checkpoint["selected_resume_sha256"] or "") != envelope.resume_sha256:
            raise ValueError("execution checkpoint resume binding changed")

        submit_rows = connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands WHERE session_id=?",
            (envelope.session_id,),
        ).fetchone()[0]
        receipt_rows = connection.execute(
            "SELECT COUNT(*) FROM application_submission_receipts WHERE session_id=?",
            (envelope.session_id,),
        ).fetchone()[0]
        if int(submit_rows) or int(receipt_rows):
            raise ValueError("execution session already has local submission authority or outcome")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def accept(
        self,
        envelope_dict: dict[str, Any],
        *,
        now: str,
    ) -> SubmitAuthorityAcceptResult:
        """Accept a Hunter-issued authority envelope.

        ``envelope_dict`` MUST be the EXACT bytes Hunter sent, re-serialised
        to a dict by the caller. We re-serialise canonically and byte-compare
        against the dict to detect any in-flight mutation.
        """
        if not production_authority_enabled():
            return SubmitAuthorityAcceptResult(
                accepted=False,
                replayed=False,
                error="production submit authority disabled",
            )

        try:
            envelope = SubmitAuthorityEnvelope.model_validate(envelope_dict)
            self._assert_fresh(envelope, now=now)
            # Unkeyed integrity: the digest must reproduce from the 24-key
            # material. The envelope signature is Hunter's attestation and is
            # only verifiable by Hunter, so it is format-checked here and
            # cryptographically proven by the claim.
            expected_auth_digest = self._expected_authority_digest(envelope)
            if not hmac.compare_digest(
                expected_auth_digest, envelope.authority_digest
            ):
                raise ValueError("submit authority digest does not match material")
            canonical = _canonical_envelope(envelope.model_dump(mode="json"))
            digest = hashlib.sha256(canonical).hexdigest()
            normalized_body = canonical
            # Stored verbatim (minus the algorithm prefix) purely so that a later
            # replay can be proven byte-identical to what Hunter originally sent.
            normalized_signature = _digest(
                envelope.signature.split("=", 1)[1],
                "Submit authority signature",
            )
        except PermissionError as error:
            return SubmitAuthorityAcceptResult(
                accepted=False,
                replayed=False,
                error=str(error),
            )
        except (ValidationError, ValueError) as error:
            return SubmitAuthorityAcceptResult(
                accepted=False,
                replayed=False,
                error=str(error),
            )

        try:
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                prior = connection.execute(
                    """SELECT body_sha256, signature
                       FROM production_submit_authorities
                       WHERE authorization_id=?""",
                    (envelope.authorization_id,),
                ).fetchone()
                if prior is not None:
                    if str(prior["body_sha256"]) == digest and hmac.compare_digest(
                        str(prior["signature"]),
                        normalized_signature,
                    ):
                        return SubmitAuthorityAcceptResult(
                            accepted=True,
                            replayed=True,
                            authorization_id=envelope.authorization_id,
                            state=CLAIM_STATE_RECEIVED,
                        )
                    return SubmitAuthorityAcceptResult(
                        accepted=False,
                        replayed=False,
                        error="submit authority replay conflict",
                    )

                self._validate_bindings_locked(connection, envelope)
                connection.execute(
                    """INSERT INTO production_submit_authorities(
                           authorization_id,tenant_id,user_id,application_id,plan_id,
                           session_id,provider,review_id,approval_id,target_url,
                           checkpoint_id,generation,plan_digest,review_digest,
                           approval_digest,prepared_package_digest,browser_form_digest,
                           resume_sha256,cover_letter_sha256,authority_digest,signature,
                           issued_at,expires_at,envelope_json,body_sha256,
                           acceptance_state,accepted_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        envelope.authorization_id,
                        envelope.tenant_id,
                        envelope.user_id,
                        envelope.application_id,
                        envelope.plan_id,
                        envelope.session_id,
                        envelope.provider.upper(),
                        envelope.review_id,
                        envelope.approval_id,
                        envelope.target_url,
                        envelope.checkpoint_id,
                        int(envelope.generation),
                        envelope.plan_digest,
                        envelope.review_digest,
                        envelope.approval_digest,
                        envelope.prepared_package_digest,
                        envelope.browser_form_digest,
                        envelope.resume_sha256,
                        envelope.cover_letter_sha256,
                        envelope.authority_digest,
                        normalized_signature,
                        envelope.issued_at,
                        envelope.expires_at,
                        normalized_body.decode("utf-8"),
                        digest,
                        "AUTHORITY_ACCEPTED",
                        datetime.now(UTC).isoformat(),
                    ),
                )
                # Initial claim row in RECEIVED state.
                claimant_id = (
                    "applypilot-"
                    + hashlib.sha256(
                        f"{envelope.authorization_id}|{digest}".encode()
                    ).hexdigest()[:32]
                )
                connection.execute(
                    """INSERT INTO production_submit_authority_claims(
                           authorization_id,claimant_id,body_sha256,state,
                           created_at,updated_at
                       ) VALUES (?,?,?,?,?,?)""",
                    (
                        envelope.authorization_id,
                        claimant_id,
                        digest,
                        CLAIM_STATE_RECEIVED,
                        datetime.now(UTC).isoformat(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except (ValueError, sqlite3.IntegrityError) as error:
            return SubmitAuthorityAcceptResult(
                accepted=False,
                replayed=False,
                error=str(error),
            )

        return SubmitAuthorityAcceptResult(
            accepted=True,
            replayed=False,
            authorization_id=envelope.authorization_id,
            state=CLAIM_STATE_RECEIVED,
        )

    def claim_for_execution(
        self,
        *,
        authorization_id: str,
        now: str,
        connection: sqlite3.Connection | None = None,
    ) -> SubmitAuthorityClaimProof:
        """Atomically claim a Hunter authority for local one-use execution.

        Transitions the claim row from RECEIVED -> CLAIM_IN_FLIGHT inside a
        single guarded UPDATE under BEGIN IMMEDIATE; if the row is already in
        CLAIM_IN_FLIGHT or any terminal state, the update is refused and the
        proof is returned as AMBIGUOUS. A second dispatch (lost response) thus
        cannot proceed to the adapter call.
        """
        if not production_authority_enabled():
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=None,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error="production submit authority disabled",
            )

        resolved = _text(authorization_id, "Authorization id")

        def _do(conn: sqlite3.Connection) -> SubmitAuthorityClaimProof:
            row = conn.execute(
                """SELECT a.application_id,a.plan_id,a.session_id,a.provider,
                          a.review_id,a.approval_id,a.authority_digest,a.generation,
                          c.claimant_id,c.body_sha256,c.state
                   FROM production_submit_authorities a
                   JOIN production_submit_authority_claims c
                     ON c.authorization_id=a.authorization_id
                   WHERE a.authorization_id=?""",
                (resolved,),
            ).fetchone()
            if row is None:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=None,
                    authority_digest=None,
                    claim_digest=None,
                    generation=None,
                    state=None,
                    error="submit authority was not accepted",
                )

            current_state = str(row["state"])
            if current_state in {
                CLAIM_STATE_CLAIMED,
                CLAIM_STATE_REJECTED,
                CLAIM_STATE_AMBIGUOUS,
            }:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=resolved,
                    authority_digest=str(row["authority_digest"]),
                    claim_digest=None,
                    generation=int(row["generation"]),
                    state=current_state,
                    error=(
                        "submit authority is "
                        f"{current_state.lower()} and cannot be re-dispatched"
                    ),
                )
            if current_state == CLAIM_STATE_IN_FLIGHT:
                # A second dispatch has already claimed-in-flight. A lost
                # response must NEVER permit a second blind submit.
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=resolved,
                    authority_digest=str(row["authority_digest"]),
                    claim_digest=None,
                    generation=int(row["generation"]),
                    state=CLAIM_STATE_AMBIGUOUS,
                    error=(
                        "submit authority claim is in-flight (lost response): "
                        "cannot dispatch"
                    ),
                )

            # RECEIVED -> CLAIM_IN_FLIGHT is the only path that advances the
            # state machine. Guarded by state at the SQL level so concurrent
            # connections cannot both succeed.
            updated = conn.execute(
                """UPDATE production_submit_authority_claims
                   SET state=?, in_flight_at=?, updated_at=?
                   WHERE authorization_id=? AND state=?""",
                (
                    CLAIM_STATE_IN_FLIGHT,
                    now,
                    datetime.now(UTC).isoformat(),
                    resolved,
                    CLAIM_STATE_RECEIVED,
                ),
            )
            if updated.rowcount != 1:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=resolved,
                    authority_digest=str(row["authority_digest"]),
                    claim_digest=None,
                    generation=int(row["generation"]),
                    state=CLAIM_STATE_AMBIGUOUS,
                    error="submit authority claim state changed during transition",
                )
            return SubmitAuthorityClaimProof(
                claimed=True,
                authorization_id=resolved,
                authority_digest=str(row["authority_digest"]),
                claim_digest=None,
                generation=int(row["generation"]),
                state=CLAIM_STATE_IN_FLIGHT,
                claimant_id=str(row["claimant_id"]),
            )

        if connection is not None:
            return _do(connection)
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                result = _do(conn)
        except (ValueError, sqlite3.IntegrityError) as error:
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=resolved,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error=str(error),
            )
        return result

    def finalize_claim(
        self,
        *,
        authorization_id: str,
        claim_digest: str,
        now: str,
    ) -> SubmitAuthorityClaimProof:
        """Transition a CLAIM_IN_FLIGHT claim to a terminal CLAIMED state.

        The ``claim_digest`` is Hunter's atomic one-time proof returned by
        ``SUBMIT_AUTHORIZATION_CLAIM``. Persisting it makes the claim final
        and inspectable. Re-running finalize on an already-CLAIMED row is a
        no-op replay.
        """
        if not production_authority_enabled():
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=None,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error="production submit authority disabled",
            )

        resolved = _text(authorization_id, "Authorization id")
        digest = _digest(claim_digest, "Claim digest")
        try:
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """SELECT a.authority_digest, a.generation, c.state,
                              c.claimant_id, c.claim_digest AS stored_claim_digest
                       FROM production_submit_authorities a
                       JOIN production_submit_authority_claims c
                         ON c.authorization_id=a.authorization_id
                       WHERE a.authorization_id=?""",
                    (resolved,),
                ).fetchone()
                if row is None:
                    return SubmitAuthorityClaimProof(
                        claimed=False,
                        authorization_id=resolved,
                        authority_digest=None,
                        claim_digest=None,
                        generation=None,
                        state=None,
                        error="submit authority was not accepted",
                    )
                # A finalize is only honourable if the digest is exactly Hunter's
                # deterministic claim receipt for THIS stored claim row. Without
                # this, any caller could promote a claim by supplying a string.
                expected_digest = hashlib.sha256(
                    _canonical_envelope(
                        {
                            "authorization_id": resolved,
                            "authority_digest": str(row["authority_digest"]),
                            "claimant_id": str(row["claimant_id"]),
                            "generation": int(row["generation"]),
                        }
                    )
                ).hexdigest()
                if not hmac.compare_digest(expected_digest, digest):
                    return SubmitAuthorityClaimProof(
                        claimed=False,
                        authorization_id=resolved,
                        authority_digest=str(row["authority_digest"]),
                        claim_digest=None,
                        generation=int(row["generation"]),
                        state=str(row["state"]),
                        error="submit authority claim digest does not match this claim",
                    )
                if str(row["state"]) == CLAIM_STATE_CLAIMED:
                    return SubmitAuthorityClaimProof(
                        claimed=True,
                        authorization_id=resolved,
                        authority_digest=str(row["authority_digest"]),
                        claim_digest=digest,
                        generation=int(row["generation"]),
                        state=CLAIM_STATE_CLAIMED,
                    )
                if str(row["state"]) != CLAIM_STATE_IN_FLIGHT:
                    return SubmitAuthorityClaimProof(
                        claimed=False,
                        authorization_id=resolved,
                        authority_digest=str(row["authority_digest"]),
                        claim_digest=None,
                        generation=int(row["generation"]),
                        state=str(row["state"]),
                        error="submit authority claim is not in-flight",
                    )
                updated = connection.execute(
                    """UPDATE production_submit_authority_claims
                       SET state=?, claim_digest=?, claimed_at=?, finalized_at=?,
                           final_error=NULL, updated_at=?
                       WHERE authorization_id=? AND state=?""",
                    (
                        CLAIM_STATE_CLAIMED,
                        digest,
                        now,
                        now,
                        datetime.now(UTC).isoformat(),
                        resolved,
                        CLAIM_STATE_IN_FLIGHT,
                    ),
                )
                if updated.rowcount != 1:
                    return SubmitAuthorityClaimProof(
                        claimed=False,
                        authorization_id=resolved,
                        authority_digest=str(row["authority_digest"]),
                        claim_digest=None,
                        generation=int(row["generation"]),
                        state=str(row["state"]),
                        error="submit authority claim state changed during finalize",
                    )
        except (ValueError, sqlite3.IntegrityError) as error:
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=resolved,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error=str(error),
            )
        return SubmitAuthorityClaimProof(
            claimed=True,
            authorization_id=resolved,
            authority_digest=str(row["authority_digest"]),
            claim_digest=digest,
            generation=int(row["generation"]),
            state=CLAIM_STATE_CLAIMED,
        )

    def mark_ambiguous(
        self,
        *,
        authorization_id: str,
        reason: str,
        now: str,
    ) -> SubmitAuthorityClaimProof:
        """Move a CLAIM_IN_FLIGHT claim into AMBIGUOUS (lost-response failure).

        The row becomes terminal; a re-dispatch will see ``AMBIGUOUS`` and
        refuse to invoke the adapter.
        """
        if not production_authority_enabled():
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=None,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error="production submit authority disabled",
            )

        resolved = _text(authorization_id, "Authorization id")
        normalized_reason = _text(reason, "Ambiguity reason", 4000)
        try:
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """SELECT a.authority_digest, a.generation, c.state
                       FROM production_submit_authorities a
                       JOIN production_submit_authority_claims c
                         ON c.authorization_id=a.authorization_id
                       WHERE a.authorization_id=?""",
                    (resolved,),
                ).fetchone()
                if row is None:
                    return SubmitAuthorityClaimProof(
                        claimed=False,
                        authorization_id=resolved,
                        authority_digest=None,
                        claim_digest=None,
                        generation=None,
                        state=None,
                        error="submit authority was not accepted",
                    )
                if str(row["state"]) == CLAIM_STATE_AMBIGUOUS:
                    return SubmitAuthorityClaimProof(
                        claimed=False,
                        authorization_id=resolved,
                        authority_digest=str(row["authority_digest"]),
                        claim_digest=None,
                        generation=int(row["generation"]),
                        state=CLAIM_STATE_AMBIGUOUS,
                        error="submit authority is already ambiguous",
                    )
                if str(row["state"]) not in {CLAIM_STATE_IN_FLIGHT, CLAIM_STATE_RECEIVED}:
                    return SubmitAuthorityClaimProof(
                        claimed=False,
                        authorization_id=resolved,
                        authority_digest=str(row["authority_digest"]),
                        claim_digest=None,
                        generation=int(row["generation"]),
                        state=str(row["state"]),
                        error="submit authority claim cannot move to ambiguous",
                    )
                connection.execute(
                    """UPDATE production_submit_authority_claims
                       SET state=?, finalized_at=?, final_error=?, updated_at=?
                       WHERE authorization_id=? AND state IN (?, ?)""",
                    (
                        CLAIM_STATE_AMBIGUOUS,
                        now,
                        normalized_reason,
                        datetime.now(UTC).isoformat(),
                        resolved,
                        CLAIM_STATE_IN_FLIGHT,
                        CLAIM_STATE_RECEIVED,
                    ),
                )
        except (ValueError, sqlite3.IntegrityError) as error:
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=resolved,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error=str(error),
            )
        return SubmitAuthorityClaimProof(
            claimed=False,
            authorization_id=resolved,
            authority_digest=str(row["authority_digest"]),
            claim_digest=None,
            generation=int(row["generation"]),
            state=CLAIM_STATE_AMBIGUOUS,
        )

    def consume_for_execution(
        self,
        *,
        session_id: str,
        now: str,
        connection: sqlite3.Connection | None = None,
    ) -> SubmitAuthorityClaimProof:
        """One-shot: claim a CLAIMED authority for the session and consume it.

        Returns the claim proof ONLY when the row is CLAIMED, has not yet been
        locally executed, and the session has no execution record yet. Inserts
        a row into ``production_submit_authority_executions`` keyed by the
        authorization_id (PK) and the session_id (UNIQUE), which together
        enforce at-most-once local execution per authority and per session.

        A second ``consume_for_execution`` for the same authorization_id (lost
        response scenario) raises an ``IntegrityError`` from the PK and is
        returned as a non-claimed proof; the caller must NOT cross the
        irreversible boundary.

        ``connection`` may be passed in to share an open parent transaction
        (e.g. from ``CompleteApplicationLoopService.submit``); otherwise a
        fresh connection is opened.
        """
        if not production_authority_enabled():
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=None,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error="production submit authority disabled",
            )

        resolved = _text(session_id, "Session id")

        def _do(conn: sqlite3.Connection) -> SubmitAuthorityClaimProof:
            row = conn.execute(
                """SELECT a.authorization_id, a.application_id, a.plan_id,
                          a.session_id, a.review_id, a.approval_id,
                          a.authority_digest, a.generation,
                          c.claimant_id, c.claim_digest, c.state
                   FROM production_submit_authorities a
                   JOIN production_submit_authority_claims c
                     ON c.authorization_id=a.authorization_id
                   WHERE a.session_id=?""",
                (resolved,),
            ).fetchone()
            if row is None:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=None,
                    authority_digest=None,
                    claim_digest=None,
                    generation=None,
                    state=None,
                    error="submit authority was not accepted for this session",
                )
            if str(row["state"]) != CLAIM_STATE_CLAIMED:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=str(row["authorization_id"]),
                    authority_digest=str(row["authority_digest"]),
                    claim_digest=None,
                    generation=int(row["generation"]),
                    state=str(row["state"]),
                    error="submit authority is not in CLAIMED state",
                )

            # UNIQUE(session_id) on the executions table blocks a second
            # execution row for the same session, and PK(authorization_id)
            # blocks a second execution row for the same authority.
            existing = conn.execute(
                """SELECT state FROM production_submit_authority_executions
                   WHERE authorization_id=?""",
                (str(row["authorization_id"]),),
            ).fetchone()
            if existing is not None:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=str(row["authorization_id"]),
                    authority_digest=str(row["authority_digest"]),
                    claim_digest=str(row["claim_digest"]) if row["claim_digest"] else None,
                    generation=int(row["generation"]),
                    state=str(row["state"]),
                    error="submit authority execution already recorded",
                )

            conn.execute(
                """INSERT INTO production_submit_authority_executions(
                       authorization_id,application_id,plan_id,session_id,
                       review_id,approval_id,claimant_id,claim_digest,
                       authority_digest,state,started_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(row["authorization_id"]),
                    str(row["application_id"]),
                    str(row["plan_id"]),
                    str(row["session_id"]),
                    str(row["review_id"]),
                    str(row["approval_id"]),
                    str(row["claimant_id"]),
                    str(row["claim_digest"]),
                    str(row["authority_digest"]),
                    "SUBMITTING",
                    now,
                ),
            )
            return SubmitAuthorityClaimProof(
                claimed=True,
                authorization_id=str(row["authorization_id"]),
                authority_digest=str(row["authority_digest"]),
                claim_digest=str(row["claim_digest"]) if row["claim_digest"] else None,
                generation=int(row["generation"]),
                state=str(row["state"]),
            )

        if connection is not None:
            try:
                return _do(connection)
            except sqlite3.IntegrityError:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=None,
                    authority_digest=None,
                    claim_digest=None,
                    generation=None,
                    state=None,
                    error="submit authority execution uniqueness conflict",
                )
            except ValueError as error:
                return SubmitAuthorityClaimProof(
                    claimed=False,
                    authorization_id=None,
                    authority_digest=None,
                    claim_digest=None,
                    generation=None,
                    state=None,
                    error=str(error),
                )
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                result = _do(conn)
        except sqlite3.IntegrityError:
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=None,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error="submit authority execution uniqueness conflict",
            )
        except ValueError as error:
            return SubmitAuthorityClaimProof(
                claimed=False,
                authorization_id=None,
                authority_digest=None,
                claim_digest=None,
                generation=None,
                state=None,
                error=str(error),
            )
        return result