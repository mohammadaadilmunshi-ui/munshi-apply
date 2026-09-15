PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS production_submit_authorities_immutable_update;
DROP TRIGGER IF EXISTS production_submit_authorities_immutable_delete;
DROP TRIGGER IF EXISTS production_submit_authority_claims_immutable_delete;
DROP TRIGGER IF EXISTS production_submit_authority_executions_terminal_immutable_update;
DROP TRIGGER IF EXISTS production_submit_authority_executions_immutable_delete;
DROP INDEX IF EXISTS idx_production_submit_authorities_session;
DROP INDEX IF EXISTS idx_production_submit_authority_claims_state;
DROP INDEX IF EXISTS idx_production_receipt_outbox_pending;

ALTER TABLE production_receipt_outbox RENAME TO production_receipt_outbox_v1;
ALTER TABLE production_submit_authority_executions RENAME TO production_submit_authority_executions_v1;
ALTER TABLE production_submit_authority_claims RENAME TO production_submit_authority_claims_v1;
ALTER TABLE production_submit_authorities RENAME TO production_submit_authorities_v1;

CREATE TABLE production_submit_authorities (
    authorization_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK(length(provider) > 0),
    review_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    target_url TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK(generation > 0),
    plan_digest TEXT NOT NULL CHECK(length(plan_digest) = 64),
    review_digest TEXT NOT NULL CHECK(length(review_digest) = 64),
    approval_digest TEXT NOT NULL CHECK(length(approval_digest) = 64),
    prepared_package_digest TEXT NOT NULL CHECK(length(prepared_package_digest) = 64),
    browser_form_digest TEXT NOT NULL CHECK(length(browser_form_digest) = 64),
    resume_sha256 TEXT NOT NULL CHECK(length(resume_sha256) = 64),
    cover_letter_sha256 TEXT CHECK(cover_letter_sha256 IS NULL OR length(cover_letter_sha256) = 64),
    authority_digest TEXT NOT NULL CHECK(length(authority_digest) = 64),
    signature TEXT NOT NULL CHECK(length(signature) = 64),
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL CHECK(expires_at > issued_at),
    envelope_json TEXT NOT NULL,
    body_sha256 TEXT NOT NULL CHECK(length(body_sha256) = 64),
    acceptance_state TEXT NOT NULL CHECK(acceptance_state = 'AUTHORITY_ACCEPTED'),
    accepted_at TEXT NOT NULL,
    UNIQUE(tenant_id, user_id, session_id, generation)
);

CREATE TABLE production_submit_authority_claims (
    authorization_id TEXT PRIMARY KEY REFERENCES production_submit_authorities(authorization_id) ON DELETE RESTRICT,
    claimant_id TEXT NOT NULL,
    body_sha256 TEXT NOT NULL CHECK(length(body_sha256) = 64),
    state TEXT NOT NULL CHECK(state IN ('RECEIVED','CLAIM_IN_FLIGHT','CLAIMED','REJECTED','AMBIGUOUS')),
    claim_digest TEXT CHECK(claim_digest IS NULL OR length(claim_digest) = 64),
    in_flight_at TEXT,
    claimed_at TEXT,
    finalized_at TEXT,
    final_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE production_submit_authority_executions (
    authorization_id TEXT PRIMARY KEY REFERENCES production_submit_authorities(authorization_id) ON DELETE RESTRICT,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL UNIQUE REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    review_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    claimant_id TEXT NOT NULL,
    claim_digest TEXT NOT NULL CHECK(length(claim_digest) = 64),
    authority_digest TEXT NOT NULL CHECK(length(authority_digest) = 64),
    state TEXT NOT NULL CHECK(state IN ('SUBMITTING','SUBMITTED','SUBMISSION_UNVERIFIED','BLOCKED','FAILED_SAFELY','VERIFIED')),
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE production_receipt_outbox (
    receipt_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE REFERENCES final_submit_commands(command_id) ON DELETE RESTRICT,
    authorization_id TEXT NOT NULL UNIQUE REFERENCES production_submit_authorities(authorization_id) ON DELETE RESTRICT,
    receipt_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('PENDING','DELIVERED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    last_error TEXT,
    delivered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO production_submit_authorities SELECT * FROM production_submit_authorities_v1;
INSERT INTO production_submit_authority_claims SELECT * FROM production_submit_authority_claims_v1;
INSERT INTO production_submit_authority_executions SELECT * FROM production_submit_authority_executions_v1;
INSERT INTO production_receipt_outbox SELECT * FROM production_receipt_outbox_v1;

DROP TABLE production_receipt_outbox_v1;
DROP TABLE production_submit_authority_executions_v1;
DROP TABLE production_submit_authority_claims_v1;
DROP TABLE production_submit_authorities_v1;

CREATE INDEX idx_production_submit_authorities_session
ON production_submit_authorities(session_id, generation DESC, accepted_at DESC);
CREATE INDEX idx_production_submit_authority_claims_state
ON production_submit_authority_claims(state, updated_at DESC);
CREATE INDEX idx_production_receipt_outbox_pending
ON production_receipt_outbox(state, updated_at);

CREATE TRIGGER production_submit_authorities_immutable_update
BEFORE UPDATE ON production_submit_authorities
BEGIN
    SELECT RAISE(ABORT, 'production submit authority inbox is immutable');
END;
CREATE TRIGGER production_submit_authorities_immutable_delete
BEFORE DELETE ON production_submit_authorities
BEGIN
    SELECT RAISE(ABORT, 'production submit authority inbox is immutable');
END;
CREATE TRIGGER production_submit_authority_claims_immutable_delete
BEFORE DELETE ON production_submit_authority_claims
BEGIN
    SELECT RAISE(ABORT, 'production submit authority claim is immutable');
END;
CREATE TRIGGER production_submit_authority_executions_terminal_immutable_update
BEFORE UPDATE ON production_submit_authority_executions
WHEN OLD.state <> 'SUBMITTING'
BEGIN
    SELECT RAISE(ABORT, 'terminal production submit authority execution is immutable');
END;
CREATE TRIGGER production_submit_authority_executions_immutable_delete
BEFORE DELETE ON production_submit_authority_executions
BEGIN
    SELECT RAISE(ABORT, 'production submit authority execution is immutable');
END;

PRAGMA foreign_keys = ON;
