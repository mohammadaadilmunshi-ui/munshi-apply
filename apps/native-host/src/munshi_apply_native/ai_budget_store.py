from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .database import Database


class AIBudgetStore:
    """Race-safe AI spend reservations backed by the authoritative SQLite ledger."""

    def __init__(self, database: Database, *, reservation_ttl_minutes: int = 15) -> None:
        if reservation_ttl_minutes < 1:
            raise ValueError("AI reservation TTL must be positive")
        self.database = database
        self.reservation_ttl = timedelta(minutes=reservation_ttl_minutes)

    @staticmethod
    def _timestamp(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("AI budget timestamp must be an ISO timestamp") from error
        if parsed.tzinfo is None:
            raise ValueError("AI budget timestamp must include a timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _money(value: float, name: str) -> float:
        amount = float(value)
        if amount < 0 or amount != amount or amount == float("inf"):
            raise ValueError(f"{name} must be a non-negative finite number")
        return round(amount, 8)

    @staticmethod
    def _month(at: datetime) -> str:
        return at.strftime("%Y-%m")

    def _release_stale(self, connection: Any, at: datetime) -> None:
        cutoff = (at - self.reservation_ttl).isoformat()
        connection.execute(
            """
            UPDATE ai_budget_reservations
            SET state = 'RELEASED', settled_at = ?
            WHERE state = 'ACTIVE' AND created_at < ?
            """,
            (at.isoformat(), cutoff),
        )

    @staticmethod
    def _totals(connection: Any, month: str) -> tuple[float, float]:
        usage = connection.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0) AS spent
            FROM ai_usage
            WHERE substr(occurred_at, 1, 7) = ?
            """,
            (month,),
        ).fetchone()
        reservations = connection.execute(
            """
            SELECT COALESCE(SUM(max_cost_usd), 0) AS reserved
            FROM ai_budget_reservations
            WHERE year_month = ? AND state = 'ACTIVE'
            """,
            (month,),
        ).fetchone()
        return round(float(usage["spent"]), 8), round(float(reservations["reserved"]), 8)

    @staticmethod
    def _decision(
        *,
        month: str,
        spent: float,
        reserved: float,
        planned: float,
        monthly_budget: float,
        warning_budget: float,
        hard_stop: bool,
    ) -> dict[str, object]:
        projected = round(spent + reserved + planned, 8)
        remaining = round(max(0.0, monthly_budget - projected), 8) if monthly_budget > 0 else 0.0
        if monthly_budget <= 0:
            state = "BLOCK"
            reason = "Monthly AI budget is zero; no paid provider usage is approved"
        elif projected > monthly_budget and hard_stop:
            state = "BLOCK"
            reason = "Projected AI request cost exceeds the configured monthly hard stop"
        elif projected > monthly_budget:
            state = "WARN"
            reason = "Projected AI request cost exceeds the monthly budget; hard stop is disabled"
        elif warning_budget > 0 and projected >= warning_budget:
            state = "WARN"
            reason = "Projected AI request cost reaches the configured warning threshold"
        else:
            state = "ALLOW"
            reason = "Projected AI request cost is within configured budget controls"
        return {
            "state": state,
            "month": month,
            "spentUsd": spent,
            "reservedUsd": reserved,
            "plannedCostUsd": planned,
            "projectedUsd": projected,
            "remainingUsd": remaining,
            "reason": reason,
        }

    def evaluate(
        self,
        *,
        planned_cost_usd: float,
        monthly_budget_usd: float,
        warning_budget_usd: float,
        hard_stop: bool,
        at: str,
    ) -> dict[str, object]:
        timestamp = self._timestamp(at)
        planned = self._money(planned_cost_usd, "planned_cost_usd")
        monthly = self._money(monthly_budget_usd, "monthly_budget_usd")
        warning = self._money(warning_budget_usd, "warning_budget_usd")
        if monthly > 0 and warning > monthly:
            raise ValueError("AI warning threshold cannot exceed monthly budget")
        month = self._month(timestamp)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._release_stale(connection, timestamp)
            spent, reserved = self._totals(connection, month)
        return self._decision(
            month=month,
            spent=spent,
            reserved=reserved,
            planned=planned,
            monthly_budget=monthly,
            warning_budget=warning,
            hard_stop=hard_stop,
        )

    def reserve(
        self,
        *,
        reservation_id: str,
        provider: str,
        model: str,
        correlation_id: str,
        planned_cost_usd: float,
        monthly_budget_usd: float,
        warning_budget_usd: float,
        hard_stop: bool,
        at: str,
    ) -> dict[str, object]:
        if (
            not reservation_id.strip()
            or not provider.strip()
            or not model.strip()
            or not correlation_id.strip()
        ):
            raise ValueError("AI reservation identifiers must not be empty")
        timestamp = self._timestamp(at)
        planned = self._money(planned_cost_usd, "planned_cost_usd")
        monthly = self._money(monthly_budget_usd, "monthly_budget_usd")
        warning = self._money(warning_budget_usd, "warning_budget_usd")
        if monthly > 0 and warning > monthly:
            raise ValueError("AI warning threshold cannot exceed monthly budget")
        month = self._month(timestamp)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._release_stale(connection, timestamp)
            existing = connection.execute(
                "SELECT * FROM ai_budget_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if existing is not None:
                raise ValueError("AI reservation identifier has already been used")
            spent, reserved = self._totals(connection, month)
            decision = self._decision(
                month=month,
                spent=spent,
                reserved=reserved,
                planned=planned,
                monthly_budget=monthly,
                warning_budget=warning,
                hard_stop=hard_stop,
            )
            if decision["state"] == "BLOCK":
                return decision
            connection.execute(
                """
                INSERT INTO ai_budget_reservations (
                    reservation_id, provider, model, year_month, max_cost_usd,
                    actual_cost_usd, state, correlation_id, created_at, settled_at
                ) VALUES (?, ?, ?, ?, ?, NULL, 'ACTIVE', ?, ?, NULL)
                """,
                (
                    reservation_id,
                    provider,
                    model,
                    month,
                    planned,
                    correlation_id,
                    timestamp.isoformat(),
                ),
            )
        return {**decision, "reservationId": reservation_id}

    def settle(
        self,
        *,
        reservation_id: str,
        usage_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        correlation_id: str,
        at: str,
        estimated: bool = False,
    ) -> bool:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("AI token usage cannot be negative")
        timestamp = self._timestamp(at)
        cost = self._money(cost_usd, "cost_usd")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            reservation = connection.execute(
                "SELECT * FROM ai_budget_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if reservation is None:
                raise ValueError("AI budget reservation does not exist")
            if reservation["state"] == "SETTLED":
                existing = connection.execute(
                    "SELECT * FROM ai_usage WHERE usage_id = ?",
                    (usage_id,),
                ).fetchone()
                if existing is None:
                    raise ValueError("Settled AI reservation is missing its usage record")
                return False
            if reservation["state"] != "ACTIVE":
                raise ValueError("AI budget reservation is no longer active")
            connection.execute(
                """
                INSERT INTO ai_usage (
                    usage_id, provider, model, occurred_at, input_tokens,
                    output_tokens, cost_usd, correlation_id, estimated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_id,
                    provider,
                    model,
                    timestamp.isoformat(),
                    int(input_tokens),
                    int(output_tokens),
                    cost,
                    correlation_id,
                    1 if estimated else 0,
                ),
            )
            connection.execute(
                """
                UPDATE ai_budget_reservations
                SET state = 'SETTLED', actual_cost_usd = ?, settled_at = ?
                WHERE reservation_id = ?
                """,
                (cost, timestamp.isoformat(), reservation_id),
            )
        return True

    def release(self, reservation_id: str, *, at: str) -> bool:
        timestamp = self._timestamp(at)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute(
                """
                UPDATE ai_budget_reservations
                SET state = 'RELEASED', settled_at = ?
                WHERE reservation_id = ? AND state = 'ACTIVE'
                """,
                (timestamp.isoformat(), reservation_id),
            )
        return result.rowcount == 1

    def usage_summary(self, *, at: str, monthly_budget_usd: float) -> dict[str, object]:
        timestamp = self._timestamp(at)
        monthly = self._money(monthly_budget_usd, "monthly_budget_usd")
        month = self._month(timestamp)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._release_stale(connection, timestamp)
            spent, reserved = self._totals(connection, month)
            row = connection.execute(
                """
                SELECT COUNT(*) AS request_count,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       COALESCE(
                           SUM(CASE WHEN estimated = 1 THEN cost_usd ELSE 0 END),
                           0
                       ) AS estimated_cost
                FROM ai_usage
                WHERE substr(occurred_at, 1, 7) = ?
                """,
                (month,),
            ).fetchone()
        return {
            "month": month,
            "spentUsd": spent,
            "reservedUsd": reserved,
            "projectedUsd": round(spent + reserved, 8),
            "remainingUsd": round(max(0.0, monthly - spent - reserved), 8) if monthly > 0 else 0.0,
            "requestCount": int(row["request_count"]),
            "inputTokens": int(row["input_tokens"]),
            "outputTokens": int(row["output_tokens"]),
            "estimatedCostUsd": round(float(row["estimated_cost"]), 8),
        }
