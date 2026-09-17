ALTER TABLE ai_usage
ADD COLUMN estimated INTEGER NOT NULL DEFAULT 0 CHECK (estimated IN (0, 1));

CREATE TABLE ai_budget_reservations (
    reservation_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    year_month TEXT NOT NULL,
    max_cost_usd REAL NOT NULL CHECK (max_cost_usd >= 0),
    actual_cost_usd REAL CHECK (actual_cost_usd IS NULL OR actual_cost_usd >= 0),
    state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'SETTLED', 'RELEASED')),
    correlation_id TEXT,
    created_at TEXT NOT NULL,
    settled_at TEXT
);

CREATE INDEX idx_ai_budget_reservations_month_state
ON ai_budget_reservations(year_month, state, created_at);
