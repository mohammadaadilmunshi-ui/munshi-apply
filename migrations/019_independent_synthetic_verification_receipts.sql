CREATE TABLE IF NOT EXISTS synthetic_submission_verification_attempts (
    attempt_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL
        REFERENCES synthetic_submit_executions(command_id) ON DELETE RESTRICT,
    verification_method TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    observed_provider TEXT NOT NULL,
    observed_provider_application_id TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK(verified IN (0,1)),
    evidence_json TEXT NOT NULL,
    evidence_digest TEXT NOT NULL CHECK(length(evidence_digest) = 64),
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(command_id, evidence_digest)
);

CREATE INDEX IF NOT EXISTS idx_synthetic_verification_attempts_command
ON synthetic_submission_verification_attempts(command_id, created_at DESC);

CREATE TABLE IF NOT EXISTS synthetic_submission_receipts (
    receipt_id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE
        REFERENCES synthetic_submit_executions(command_id) ON DELETE RESTRICT,
    application_id TEXT NOT NULL
        REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    review_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    provider TEXT NOT NULL CHECK(provider = 'GREENHOUSE'),
    provider_application_id TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    verification_method TEXT NOT NULL
        CHECK(verification_method = 'SYNTHETIC_PROVIDER_LOOKUP'),
    verification_attempt_id TEXT NOT NULL UNIQUE
        REFERENCES synthetic_submission_verification_attempts(attempt_id) ON DELETE RESTRICT,
    verification_evidence_json TEXT NOT NULL,
    verification_evidence_digest TEXT NOT NULL
        CHECK(length(verification_evidence_digest) = 64),
    plan_digest TEXT NOT NULL CHECK(length(plan_digest) = 64),
    review_digest TEXT NOT NULL CHECK(length(review_digest) = 64),
    approval_digest TEXT NOT NULL CHECK(length(approval_digest) = 64),
    prepared_package_digest TEXT NOT NULL CHECK(length(prepared_package_digest) = 64),
    browser_form_digest TEXT NOT NULL CHECK(length(browser_form_digest) = 64),
    resume_sha256 TEXT NOT NULL CHECK(length(resume_sha256) = 64),
    cover_letter_sha256 TEXT
        CHECK(cover_letter_sha256 IS NULL OR length(cover_letter_sha256) = 64),
    answers_digest TEXT NOT NULL CHECK(length(answers_digest) = 64),
    execution_result_digest TEXT NOT NULL CHECK(length(execution_result_digest) = 64),
    execution_chain_digest TEXT NOT NULL CHECK(length(execution_chain_digest) = 64),
    receipt_json TEXT NOT NULL,
    receipt_digest TEXT NOT NULL UNIQUE CHECK(length(receipt_digest) = 64),
    verification_status TEXT NOT NULL CHECK(verification_status = 'VERIFIED'),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_synthetic_submission_receipts_application
ON synthetic_submission_receipts(application_id, verified_at DESC);

CREATE TRIGGER IF NOT EXISTS synthetic_verification_attempts_immutable_update
BEFORE UPDATE ON synthetic_submission_verification_attempts
BEGIN
    SELECT RAISE(ABORT, 'synthetic verification attempt is immutable');
END;

CREATE TRIGGER IF NOT EXISTS synthetic_verification_attempts_immutable_delete
BEFORE DELETE ON synthetic_submission_verification_attempts
BEGIN
    SELECT RAISE(ABORT, 'synthetic verification attempt is immutable');
END;

CREATE TRIGGER IF NOT EXISTS synthetic_submission_receipts_immutable_update
BEFORE UPDATE ON synthetic_submission_receipts
BEGIN
    SELECT RAISE(ABORT, 'synthetic submission receipt is immutable');
END;

CREATE TRIGGER IF NOT EXISTS synthetic_submission_receipts_immutable_delete
BEFORE DELETE ON synthetic_submission_receipts
BEGIN
    SELECT RAISE(ABORT, 'synthetic submission receipt is immutable');
END;
