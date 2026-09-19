from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4


class MechanicsRecoveryCoordinator:
    """Runs promoted Teach before Sonnet and accepts only deterministic verification."""

    def __init__(
        self,
        *,
        fallback_service: Any,
        teach_service: Any = None,
        teach_dispatcher: Callable[[Callable[[], None]], None] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.fallback_service = fallback_service
        self.teach_service = teach_service
        self.teach_dispatcher = teach_dispatcher or (lambda task: task())
        self.on_event = on_event or (lambda _kind, _payload: None)

    def _recipe(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        recipes = getattr(self.teach_service, "recipes", None)
        lookup = getattr(recipes, "lookup", None)
        if not callable(lookup):
            return None
        try:
            value = lookup(payload)
        except Exception:
            return None
        if not isinstance(value, dict) or str(value.get("state") or "").upper() != "PROMOTED":
            return None
        return value

    def _record_recipe(
        self,
        *,
        plan: dict[str, Any],
        recipe: dict[str, Any],
        success: bool,
    ) -> None:
        recipes = getattr(self.teach_service, "recipes", None)
        record = getattr(recipes, "record_outcome", None)
        recipe_id = str(recipe.get("recipeId") or "")
        if not callable(record) or not recipe_id:
            return
        try:
            record(
                {
                    "recipeId": recipe_id,
                    "attemptId": f"mechanics-recipe-{uuid4().hex}",
                    "applicationId": str(plan.get("application_id") or "") or None,
                    "success": bool(success),
                    "verified": True,
                    "failureReason": None if success else "mechanics_recipe_failed_verification",
                }
            )
        except Exception:
            return

    def _capture(
        self,
        *,
        plan: dict[str, Any],
        payload: dict[str, Any],
        proposal: dict[str, Any],
        context_fingerprint: str,
    ) -> None:
        capture = getattr(self.teach_service, "capture", None)
        if not callable(capture):
            return
        actions = proposal.get("actions")
        identity = json.dumps(
            {
                "application": str(plan.get("application_id") or ""),
                "component": payload.get("componentFingerprint"),
                "context": context_fingerprint,
                "actions": actions,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        lesson = {
            "observationId": "obs-"
            + hashlib.sha256(identity.encode()).hexdigest()[:32],
            "applicationId": str(plan.get("application_id") or "") or None,
            "siteOrigin": payload["siteOrigin"],
            "componentFingerprint": payload["componentFingerprint"],
            "semanticType": payload["semanticType"],
            "atsFamily": payload.get("atsFamily"),
            "tenantKey": payload.get("tenantKey"),
            "uiFingerprint": payload.get("uiFingerprint"),
            "questionFingerprint": payload.get("questionFingerprint"),
            "teacherKind": str(proposal.get("teacherKind") or "MODEL").upper(),
            "teacherProvider": (
                str(proposal.get("provider")) if proposal.get("provider") else None
            ),
            "sourceLane": str(
                proposal.get("sourceLane") or "AUTOAPPLY_MECHANICS_FALLBACK"
            ),
            "actions": actions,
            "verifiedSuccess": True,
        }

        def task() -> None:
            try:
                capture(lesson)
            except Exception:
                return

        try:
            self.teach_dispatcher(task)
        except Exception:
            return

    def attempt(
        self,
        *,
        plan: dict[str, Any],
        payload: dict[str, Any],
        executor: Any,
        allowed_value_refs: set[str],
        verify: Callable[[], bool],
        context_fingerprint: str,
    ) -> str | None:
        recipe = self._recipe(payload)
        if recipe is not None:
            success = False
            try:
                executor.execute(
                    recipe.get("actions"),
                    allowed_value_refs=allowed_value_refs,
                )
                success = verify() is True
            except Exception:
                try:
                    success = verify() is True
                except Exception:
                    success = False
            self._record_recipe(plan=plan, recipe=recipe, success=success)
            if success:
                self.on_event(
                    "MECHANICS_VERIFIED",
                    {
                        "source": "PROMOTED_RECIPE",
                        "component_fingerprint": payload.get("componentFingerprint"),
                    },
                )
                return "PROMOTED_RECIPE"

        proposal: dict[str, Any] | None = None
        try:
            candidate = self.fallback_service.propose(payload)
            if isinstance(candidate, dict):
                proposal = candidate
                executor.execute(
                    proposal.get("actions"),
                    allowed_value_refs=allowed_value_refs,
                )
        except Exception:
            return None
        if proposal is None:
            return None
        try:
            success = verify() is True
        except Exception:
            success = False
        if not success:
            return None
        self.on_event(
            "MECHANICS_VERIFIED",
            {
                "source": "MODEL_FALLBACK",
                "component_fingerprint": payload.get("componentFingerprint"),
            },
        )
        self._capture(
            plan=plan,
            payload=payload,
            proposal=proposal,
            context_fingerprint=context_fingerprint,
        )
        return "MODEL_FALLBACK"
