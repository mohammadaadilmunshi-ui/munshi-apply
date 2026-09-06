-- Phase 9: inbound Career OS preparation packages.  This is an audit/hand-off
-- ledger only; it intentionally creates no provider submission capability.
CREATE TABLE career_os_preparation_handoffs (
    handoff_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    package_id TEXT NOT NULL,
    package_version INTEGER NOT NULL CHECK (package_version > 0),
    job_id TEXT NOT NULL,
    preparation_id TEXT,
    application_identity TEXT NOT NULL,
    provider TEXT NOT NULL,
    handoff_state TEXT NOT NULL CHECK (handoff_state IN ('PREPARED', 'NEEDS_INPUT', 'READY_TO_APPLY', 'HANDOFF_ACCEPTED')),
    idempotency_key TEXT NOT NULL,
    body_sha256 TEXT NOT NULL CHECK (length(body_sha256) = 64),
    package_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    UNIQUE (tenant_id, user_id, idempotency_key),
    UNIQUE (tenant_id, package_id, package_version)
);

CREATE INDEX idx_career_os_handoffs_tenant_received
ON career_os_preparation_handoffs(tenant_id, received_at);
