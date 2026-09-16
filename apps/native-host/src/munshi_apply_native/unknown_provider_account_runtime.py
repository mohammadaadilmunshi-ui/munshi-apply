from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .account_teach_service import AccountTeachError, AccountTeachService
from .database import Database


class UnknownProviderAccountRuntimeError(RuntimeError):
    pass


class AccountRecipeExecutor(Protocol):
    def execute_recipe(self, actions: list[dict[str, object]]) -> bool: ...


class AccountFallbackExecutor(Protocol):
    def execute_fallback(self) -> "VerifiedFallbackOutcome": ...


@dataclass(frozen=True)
class VerifiedFallbackOutcome:
    verified_success: bool
    actions: list[dict[str, object]]
    failure_reason: str | None = None


@dataclass(frozen=True)
class UnknownProviderAccountResult:
    state: str
    source: str
    recipe_id: str | None
    lesson_id: str | None
    continuation_allowed: bool
    issue_code: str | None


class UnknownProviderAccountRuntime:
    """Use promoted account mechanics first, then a verified fail-closed fallback.

    SHADOW lessons are deliberately not allowed to auto-act. They are learned
    asynchronously from verified fallback outcomes and become executable only after
    promotion. This runtime never receives password/code/link values and has no
    application-submit authority.
    """

    def __init__(self, database: Database) -> None:
        self.teach = AccountTeachService(database)

    @staticmethod
    def _lookup_payload(context: dict[str, object]) -> dict[str, object]:
        required = (
            "siteOrigin",
            "componentFingerprint",
            "semanticType",
        )
        if any(not str(context.get(key) or "").strip() for key in required):
            raise UnknownProviderAccountRuntimeError(
                "Unknown-provider account context is incomplete"
            )
        return {
            "siteOrigin": context["siteOrigin"],
            "componentFingerprint": context["componentFingerprint"],
            "semanticType": context["semanticType"],
            "atsFamily": context.get("atsFamily"),
            "tenantKey": context.get("tenantKey"),
            "uiFingerprint": context.get("uiFingerprint"),
        }

    @staticmethod
    def _issue(
        *,
        source: str,
        recipe_id: str | None,
        issue_code: str,
    ) -> UnknownProviderAccountResult:
        return UnknownProviderAccountResult(
            state="ISSUE",
            source=source,
            recipe_id=recipe_id,
            lesson_id=None,
            continuation_allowed=False,
            issue_code=issue_code,
        )

    def execute(
        self,
        *,
        context: dict[str, object],
        application_id: str | None,
        occurred_at: str,
        recipe_executor: AccountRecipeExecutor,
        fallback_executor: AccountFallbackExecutor,
    ) -> UnknownProviderAccountResult:
        lookup = self._lookup_payload(context)
        promoted = self.teach.lookup_promoted(lookup)
        promoted_recipe_id = (
            str(promoted["recipe_id"]) if promoted is not None else None
        )

        if promoted is not None:
            actions = promoted.get("actions")
            if not isinstance(actions, list):
                raise UnknownProviderAccountRuntimeError(
                    "Promoted account recipe has invalid actions"
                )
            try:
                recipe_success = recipe_executor.execute_recipe(actions)
            except Exception:
                recipe_success = False
            self.teach.record_verified_outcome(
                promoted_recipe_id,
                application_id=application_id,
                success=recipe_success is True,
                occurred_at=occurred_at,
                failure_reason=(
                    None if recipe_success is True else "promoted_recipe_failed"
                ),
            )
            if recipe_success is True:
                return UnknownProviderAccountResult(
                    state="CONTINUE",
                    source="PROMOTED_RECIPE",
                    recipe_id=promoted_recipe_id,
                    lesson_id=None,
                    continuation_allowed=True,
                    issue_code=None,
                )

        try:
            outcome = fallback_executor.execute_fallback()
        except Exception:
            return self._issue(
                source="FALLBACK",
                recipe_id=promoted_recipe_id,
                issue_code="UNKNOWN_PROVIDER_ACCOUNT_FALLBACK_FAILED",
            )

        if outcome.verified_success is not True:
            return self._issue(
                source="FALLBACK",
                recipe_id=promoted_recipe_id,
                issue_code="UNKNOWN_PROVIDER_ACCOUNT_MECHANIC_UNVERIFIED",
            )

        capture_payload = {
            "observationId": f"account-fallback-{uuid4().hex}",
            "applicationId": application_id,
            **lookup,
            "actions": outcome.actions,
            "verifiedSuccess": True,
        }
        try:
            captured = self.teach.capture(capture_payload)
        except AccountTeachError as error:
            raise UnknownProviderAccountRuntimeError(
                "Verified fallback could not be captured safely"
            ) from error

        return UnknownProviderAccountResult(
            state="CONTINUE",
            source="VERIFIED_FALLBACK",
            recipe_id=promoted_recipe_id,
            lesson_id=str(captured["lessonId"]),
            continuation_allowed=True,
            issue_code=None,
        )
