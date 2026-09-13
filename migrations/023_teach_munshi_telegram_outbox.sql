PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teach_munshi_telegram_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teach_munshi_telegram_outbox (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'RECIPE_PROMOTED',
        'RECIPE_ROLLED_BACK',
        'LEARNING_FAILED'
    )),
    payload_json TEXT NOT NULL,
    delivery_state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK(delivery_state IN (
            'PENDING',
            'DELIVERING',
            'DELIVERED',
            'DEAD_LETTER'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    next_attempt_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_teach_munshi_tg_due
ON teach_munshi_telegram_outbox(
    delivery_state,
    next_attempt_at,
    created_at
);
