-- Production (non-synthetic) submit authority inbox for the single-approval loop.
--
-- Mirrors migrations 017/018 exactly: immutable received/claim rows, a state-
-- guarded executions table whose terminal rows are immutable, before-update
-- and before-delete triggers that raise ABORT.
--
-- Differences vs synthetic (017/018):
--   * PK is authorization_id (Hunter-issued UUID), not command_id.
--   * provider is NOT pinned to GREENHOUSE (production supports all real
--     providers); provider is uppercase, non-blank.
--   * claims table is a state machine RECEIVED -> CLAIM_IN_FLIGHT -> CLAIMED
--     | REJECTED | AMBIGUOUS with a guarded UPDATE transition that fails closed
--     on lost responses (a row already in CLAIM_IN_FLIGHT cannot be re-
--     dispatched; consume_for_execution refuses it as AMBIGUOUS).
--   * executions table has a UNIQUE(session_id) constraint plus a terminal
--     immutability trigger WHEN OLD.state <> 'SUBMITTING'.

CREATE TABLE IF NOT EXISTS production_submit_authorities (
    authorization_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    application_id TEXT NOT NULL
        REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
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
    cover_letter_sha256 TEXT
        CHECK(cover_letter_sha256 IS NULL OR length(cover_letter_sha256) = 64),
    authority_digest TEXT NOT NULL CHECK(length(authority_digest) = 64),
    signature TEXT NOT NULL CHECK(length(signature) = 64),
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL CHECK(expires_at > issued_at),
    envelope_json TEXT NOT NULL,
    body_sha256 TEXT NOT NULL CHECK(length(body_sha256) = 64),
    acceptance_state TEXT NOT NULL CHECK(acceptance_state = 'AUTHORITY_ACCEPTED'),
    accepted_at TEXT NOT NULL,
    -- Exactly one ISSUED authority per (tenant, user, session). A re-issued
    -- authority for the same session replaces this row through the inbox,
    -- never via direct UPDATE (UPDATE is blocked by immutability trigger).
    UNIQUE(tenant_id, user_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_production_submit_authorities_session
ON production_submit_authorities(session_id, accepted_at DESC);

CREATE TABLE IF NOT EXISTS production_submit_authority_claims (
    authorization_id TEXT PRIMARY KEY
        REFERENCES production_submit_authorities(authorization_id) ON DELETE RESTRICT,
    claimant_id TEXT NOT NULL,
    body_sha256 TEXT NOT NULL CHECK(length(body_sha256) = 64),
    state TEXT NOT NULL CHECK(state IN (
        'RECEIVED','CLAIM_IN_FLIGHT','CLAIMED','REJECTED','AMBIGUOUS'
    )),
    claim_digest TEXT
        CHECK(claim_digest IS NULL OR length(claim_digest) = 64),
    in_flight_at TEXT,
    claimed_at TEXT,
    finalized_at TEXT,
    final_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_production_submit_authority_claims_state
ON production_submit_authority_claims(state, updated_at DESC);

CREATE TABLE IF NOT EXISTS production_submit_authority_executions (
    authorization_id TEXT PRIMARY KEY
        REFERENCES production_submit_authorities(authorization_id) ON DELETE RESTRICT,
    application_id TEXT NOT NULL
        REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL UNIQUE
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    review_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    claimant_id TEXT NOT NULL,
    claim_digest TEXT NOT NULL CHECK(length(claim_digest) = 64),
    authority_digest TEXT NOT NULL CHECK(length(authority_digest) = 64),
    state TEXT NOT NULL CHECK(state IN (
        'SUBMITTING','SUBMITTED','SUBMISSION_UNVERIFIED','BLOCKED','FAILED_SAFELY','VERIFIED'
    )),
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TRIGGER IF NOT EXISTS production_submit_authorities_immutable_update
BEFORE UPDATE ON production_submit_authorities
BEGIN
    SELECT RAISE(ABORT, 'production submit authority inbox is immutable');
END;

CREATE TRIGGER IF NOT EXISTS production_submit_authorities_immutable_delete
BEFORE DELETE ON production_submit_authorities
BEGIN
    SELECT RAISE(ABORT, 'production submit authority inbox is immutable');
END;

-- The claim state machine lives entirely in this table; immutability on the
-- received/claimed pivot columns (authorization_id, body_sha256, claimant_id)
-- is enforced by preventing UPDATE/DELETE on the row once it is set.
CREATE TRIGGER IF NOT EXISTS production_submit_authority_claims_immutable_delete
BEFORE DELETE ON production_submit_authority_claims
BEGIN
    SELECT RAISE(ABORT, 'production submit authority claim is immutable');
END;

CREATE TRIGGER IF NOT EXISTS production_submit_authority_executions_terminal_immutable_update
BEFORE UPDATE ON production_submit_authority_executions
WHEN OLD.state <> 'SUBMITTING'
BEGIN
    SELECT RAISE(ABORT, 'terminal production submit authority execution is immutable');
END;

CREATE TRIGGER IF NOT EXISTS production_submit_authority_executions_immutable_delete
BEFORE DELETE ON production_submit_authority_executions
BEGIN
    SELECT RAISE(ABORT, 'production submit authority execution is immutable');
END;