CREATE TABLE IF NOT EXISTS synthetic_submit_command_inbox (
    command_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    application_id TEXT NOT NULL
        REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK(provider = 'GREENHOUSE'),
    review_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    fixture_job_id INTEGER NOT NULL CHECK(fixture_job_id > 0),
    target_url TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    review_digest TEXT NOT NULL CHECK(length(review_digest) = 64),
    approval_digest TEXT NOT NULL CHECK(length(approval_digest) = 64),
    plan_digest TEXT NOT NULL CHECK(length(plan_digest) = 64),
    prepared_package_digest TEXT NOT NULL CHECK(length(prepared_package_digest) = 64),
    browser_form_digest TEXT NOT NULL CHECK(length(browser_form_digest) = 64),
    resume_sha256 TEXT NOT NULL CHECK(length(resume_sha256) = 64),
    cover_letter_sha256 TEXT
        CHECK(cover_letter_sha256 IS NULL OR length(cover_letter_sha256) = 64),
    issued_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL CHECK(expires_at > issued_at),
    envelope_json TEXT NOT NULL,
    body_sha256 TEXT NOT NULL CHECK(length(body_sha256) = 64),
    signature TEXT NOT NULL CHECK(length(signature) = 64),
    acceptance_state TEXT NOT NULL CHECK(acceptance_state = 'COMMAND_ACCEPTED'),
    accepted_at TEXT NOT NULL,
    UNIQUE(tenant_id, user_id, approval_id)
);

CREATE INDEX IF NOT EXISTS idx_synthetic_submit_command_inbox_session
ON synthetic_submit_command_inbox(session_id, accepted_at DESC);

CREATE TABLE IF NOT EXISTS synthetic_submit_command_claims (
    command_id TEXT PRIMARY KEY
        REFERENCES synthetic_submit_command_inbox(command_id) ON DELETE RESTRICT,
    body_sha256 TEXT NOT NULL CHECK(length(body_sha256) = 64),
    claimed_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS synthetic_submit_command_inbox_immutable_update
BEFORE UPDATE ON synthetic_submit_command_inbox
BEGIN
    SELECT RAISE(ABORT, 'synthetic submit command inbox is immutable');
END;

CREATE TRIGGER IF NOT EXISTS synthetic_submit_command_inbox_immutable_delete
BEFORE DELETE ON synthetic_submit_command_inbox
BEGIN
    SELECT RAISE(ABORT, 'synthetic submit command inbox is immutable');
END;

CREATE TRIGGER IF NOT EXISTS synthetic_submit_command_claims_immutable_update
BEFORE UPDATE ON synthetic_submit_command_claims
BEGIN
    SELECT RAISE(ABORT, 'synthetic submit command claim is immutable');
END;

CREATE TRIGGER IF NOT EXISTS synthetic_submit_command_claims_immutable_delete
BEFORE DELETE ON synthetic_submit_command_claims
BEGIN
    SELECT RAISE(ABORT, 'synthetic submit command claim is immutable');
END;
