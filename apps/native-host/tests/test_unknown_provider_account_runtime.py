from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.unknown_provider_account_runtime import (
    UnknownProviderAccountRuntime,
    VerifiedFallbackOutcome,
)

NOW = "2026-09-16T18:00:00+00:00"


def _runtime(tmp_path: Path) -> tuple[Database, UnknownProviderAccountRuntime]:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "unknown-provider.sqlite", migrations)
    database.migrate()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO applications(
                application_id, job_id, status, resume_id, job_signal_score,
                submitted_at, created_at, updated_at
            ) VALUES('app-unknown',NULL,'DETECTED',NULL,NULL,NULL,?,?)
            """,
            (NOW, NOW),
        )
    return database, UnknownProviderAccountRuntime(database)


def _context() -> dict[str, object]:
    return {
        "siteOrigin": "https://unknown-ats.example",
        "componentFingerprint": "cfp-account-unknown",
        "semanticType": "ATS_ACCOUNT_MAGIC_LOGIN",
        "atsFamily": "UNKNOWN",
        "tenantKey": "example-tenant",
        "uiFingerprint": "unknown-account-ui-v1",
    }


@dataclass
class RecipeExecutor:
    success: bool = True
    calls: int = 0

    def execute_recipe(self, actions: list[dict[str, object]]) -> bool:
        self.calls += 1
        assert actions
        return self.success


@dataclass
class FallbackExecutor:
    outcome: VerifiedFallbackOutcome
    calls: int = 0
    raises: bool = False

    def execute_fallback(self) -> VerifiedFallbackOutcome:
        self.calls += 1
        if self.raises:
            raise RuntimeError("fixture fallback failure")
        return self.outcome


def _verified_fallback() -> FallbackExecutor:
    return FallbackExecutor(
        VerifiedFallbackOutcome(
            verified_success=True,
            actions=[{"type": "OPEN_VERIFICATION_LINK"}],
        )
    )


def test_verified_fallback_continues_and_only_queues_async_teach(tmp_path: Path) -> None:
    database, runtime = _runtime(tmp_path)
    recipe = RecipeExecutor()
    fallback = _verified_fallback()

    result = runtime.execute(
        context=_context(),
        application_id="app-unknown",
        occurred_at=NOW,
        recipe_executor=recipe,
        fallback_executor=fallback,
    )

    assert result.state == "CONTINUE"
    assert result.source == "VERIFIED_FALLBACK"
    assert result.continuation_allowed is True
    assert result.lesson_id is not None
    assert recipe.calls == 0
    assert fallback.calls == 1

    with database.connect() as connection:
        lesson = connection.execute(
            "SELECT state FROM ats_teach_lessons WHERE lesson_id=?",
            (result.lesson_id,),
        ).fetchone()
        assert lesson[0] == "PENDING"
        assert connection.execute(
            "SELECT COUNT(*) FROM interaction_recipes"
        ).fetchone()[0] == 0


def test_unverified_or_failed_fallback_becomes_issue_without_teaching(tmp_path: Path) -> None:
    database, runtime = _runtime(tmp_path)
    recipe = RecipeExecutor()
    unverified = FallbackExecutor(
        VerifiedFallbackOutcome(
            verified_success=False,
            actions=[{"type": "OPEN_VERIFICATION_LINK"}],
            failure_reason="not independently verified",
        )
    )

    blocked = runtime.execute(
        context=_context(),
        application_id="app-unknown",
        occurred_at=NOW,
        recipe_executor=recipe,
        fallback_executor=unverified,
    )
    assert blocked.state == "ISSUE"
    assert blocked.continuation_allowed is False
    assert blocked.issue_code == "UNKNOWN_PROVIDER_ACCOUNT_MECHANIC_UNVERIFIED"

    failed = runtime.execute(
        context=_context(),
        application_id="app-unknown",
        occurred_at=NOW,
        recipe_executor=recipe,
        fallback_executor=FallbackExecutor(
            VerifiedFallbackOutcome(True, [{"type": "OPEN_VERIFICATION_LINK"}]),
            raises=True,
        ),
    )
    assert failed.state == "ISSUE"
    assert failed.continuation_allowed is False
    assert failed.issue_code == "UNKNOWN_PROVIDER_ACCOUNT_FALLBACK_FAILED"

    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ats_teach_lessons"
        ).fetchone()[0] == 0


def test_unknown_provider_learns_promotes_then_reuses_recipe(tmp_path: Path) -> None:
    _database, runtime = _runtime(tmp_path)
    recipe = RecipeExecutor(success=True)

    # No promoted recipe exists yet, so each verified fallback continues the
    # application immediately and queues a secretless lesson. Draining simulates
    # the asynchronous Teach worker after the application has already continued.
    for _ in range(3):
        fallback = _verified_fallback()
        result = runtime.execute(
            context=_context(),
            application_id="app-unknown",
            occurred_at=NOW,
            recipe_executor=recipe,
            fallback_executor=fallback,
        )
        assert result.source == "VERIFIED_FALLBACK"
        assert result.continuation_allowed is True
        assert fallback.calls == 1
        assert runtime.teach.drain(limit=1)["learned"] == 1

    promoted = runtime.teach.lookup_promoted(_context())
    assert promoted is not None
    assert promoted["state"] == "PROMOTED"
    assert promoted["verified_successes"] == 3

    fallback = _verified_fallback()
    reused = runtime.execute(
        context=_context(),
        application_id="app-unknown",
        occurred_at=NOW,
        recipe_executor=recipe,
        fallback_executor=fallback,
    )
    assert reused.state == "CONTINUE"
    assert reused.source == "PROMOTED_RECIPE"
    assert reused.recipe_id == promoted["recipe_id"]
    assert reused.lesson_id is None
    assert reused.continuation_allowed is True
    assert recipe.calls == 1
    assert fallback.calls == 0


def test_repeated_promoted_recipe_failures_roll_back_and_use_verified_fallback(
    tmp_path: Path,
) -> None:
    _database, runtime = _runtime(tmp_path)
    learning_recipe = RecipeExecutor(success=True)
    for _ in range(3):
        result = runtime.execute(
            context=_context(),
            application_id="app-unknown",
            occurred_at=NOW,
            recipe_executor=learning_recipe,
            fallback_executor=_verified_fallback(),
        )
        assert result.continuation_allowed is True
        runtime.teach.drain(limit=1)

    promoted = runtime.teach.lookup_promoted(_context())
    assert promoted is not None

    failing_recipe = RecipeExecutor(success=False)
    first_fallback = _verified_fallback()
    first = runtime.execute(
        context=_context(),
        application_id="app-unknown",
        occurred_at="2026-09-16T18:01:00+00:00",
        recipe_executor=failing_recipe,
        fallback_executor=first_fallback,
    )
    assert first.source == "VERIFIED_FALLBACK"
    assert first.continuation_allowed is True
    assert first_fallback.calls == 1

    second_fallback = _verified_fallback()
    second = runtime.execute(
        context=_context(),
        application_id="app-unknown",
        occurred_at="2026-09-16T18:02:00+00:00",
        recipe_executor=failing_recipe,
        fallback_executor=second_fallback,
    )
    assert second.source == "VERIFIED_FALLBACK"
    assert second.continuation_allowed is True
    assert second_fallback.calls == 1
    assert runtime.teach.lookup_promoted(_context()) is None
