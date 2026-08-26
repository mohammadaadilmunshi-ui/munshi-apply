ALTER TABLE application_events
ADD COLUMN schema_version TEXT NOT NULL DEFAULT '1.0';

ALTER TABLE application_events
ADD COLUMN correlation_id TEXT;

ALTER TABLE application_events
ADD COLUMN payload_sha256 TEXT;

CREATE TABLE outbox_events (
    event_id TEXT PRIMARY KEY REFERENCES application_events(event_id) ON DELETE CASCADE,
    schema_version TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    application_id TEXT REFERENCES applications(application_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (delivery_status IN ('PENDING', 'IN_FLIGHT', 'DELIVERED', 'RETRY', 'DEAD_LETTER')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempt_at TEXT,
    next_retry_at TEXT,
    delivered_at TEXT,
    last_error TEXT
);

CREATE INDEX idx_outbox_delivery_due
ON outbox_events(delivery_status, next_retry_at, created_at);

CREATE INDEX idx_outbox_correlation
ON outbox_events(correlation_id, created_at);
