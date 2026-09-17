CREATE TABLE IF NOT EXISTS production_receipt_outbox (
    receipt_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE
        REFERENCES final_submit_commands(command_id) ON DELETE RESTRICT,
    authorization_id TEXT NOT NULL UNIQUE
        REFERENCES production_submit_authorities(authorization_id) ON DELETE RESTRICT,
    receipt_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('PENDING','DELIVERED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    last_error TEXT,
    delivered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_production_receipt_outbox_pending
ON production_receipt_outbox(state, updated_at);
