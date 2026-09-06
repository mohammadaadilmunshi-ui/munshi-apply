CREATE TABLE IF NOT EXISTS career_os_application_plans (
    plan_id TEXT PRIMARY KEY,
    handoff_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    application_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    plan_version TEXT NOT NULL,
    plan_digest TEXT NOT NULL CHECK(length(plan_digest) = 64),
    job_snapshot_sha256 TEXT NOT NULL CHECK(length(job_snapshot_sha256) = 64),
    resume_artifact_id TEXT NOT NULL,
    resume_artifact_sha256 TEXT NOT NULL CHECK(length(resume_artifact_sha256) = 64),
    body_sha256 TEXT NOT NULL CHECK(length(body_sha256) = 64),
    idempotency_key TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    acceptance_state TEXT NOT NULL CHECK(acceptance_state = 'PLAN_ACCEPTED'),
    accepted_at TEXT NOT NULL,
    UNIQUE(tenant_id, user_id, idempotency_key),
    UNIQUE(tenant_id, user_id, plan_digest)
);

CREATE INDEX IF NOT EXISTS idx_career_os_application_plans_application
ON career_os_application_plans(application_id, accepted_at DESC);

CREATE TABLE IF NOT EXISTS complete_application_sessions (
    session_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN (
        'PLAN_ACCEPTED','SESSION_STARTING','JOB_VERIFIED','FORM_DISCOVERED',
        'PREPARING','NEEDS_INPUT','READY_FOR_REVIEW','READY_TO_SUBMIT',
        'SUBMITTING','SUBMITTED','VERIFIED','SUBMISSION_UNVERIFIED',
        'BLOCKED','FAILED_SAFELY'
    )),
    state_version INTEGER NOT NULL DEFAULT 1 CHECK(state_version >= 1),
    current_url TEXT,
    observed_job_identity TEXT,
    browser_form_digest TEXT,
    checkpoint_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(application_id, plan_id)
);

CREATE INDEX IF NOT EXISTS idx_complete_application_sessions_state
ON complete_application_sessions(state, updated_at DESC);

CREATE TABLE IF NOT EXISTS complete_application_execution_events (
    event_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    replay_identity TEXT NOT NULL UNIQUE,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    checkpoint_json TEXT,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_complete_application_execution_events_chain
ON complete_application_execution_events(application_id, plan_id, session_id, occurred_at, event_id);

CREATE TABLE IF NOT EXISTS final_application_reviews (
    review_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    review_digest TEXT NOT NULL CHECK(length(review_digest) = 64),
    plan_digest TEXT NOT NULL CHECK(length(plan_digest) = 64),
    browser_form_digest TEXT NOT NULL CHECK(length(browser_form_digest) = 64),
    resume_digest TEXT NOT NULL CHECK(length(resume_digest) = 64),
    review_json TEXT NOT NULL,
    approved_at TEXT,
    invalidated_at TEXT,
    invalidation_reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(application_id, plan_id, review_digest)
);

CREATE INDEX IF NOT EXISTS idx_final_application_reviews_current
ON final_application_reviews(application_id, plan_id, created_at DESC);

CREATE TABLE IF NOT EXISTS final_submit_commands (
    command_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    review_id TEXT NOT NULL REFERENCES final_application_reviews(review_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL UNIQUE,
    command_digest TEXT NOT NULL CHECK(length(command_digest) = 64),
    state TEXT NOT NULL CHECK(state IN (
        'READY_TO_SUBMIT','SUBMITTING','SUBMITTED','VERIFIED',
        'SUBMISSION_UNVERIFIED','BLOCKED','FAILED_SAFELY'
    )),
    issued_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_final_submit_commands_once_per_review
ON final_submit_commands(application_id, plan_id, review_id);

CREATE TABLE IF NOT EXISTS application_submission_receipts (
    receipt_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    review_id TEXT NOT NULL REFERENCES final_application_reviews(review_id) ON DELETE RESTRICT,
    command_id TEXT NOT NULL REFERENCES final_submit_commands(command_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    submission_url TEXT,
    provider_application_id TEXT,
    resume_artifact_id TEXT NOT NULL,
    resume_sha256 TEXT NOT NULL CHECK(length(resume_sha256) = 64),
    answers_digest TEXT NOT NULL CHECK(length(answers_digest) = 64),
    execution_chain_digest TEXT NOT NULL CHECK(length(execution_chain_digest) = 64),
    verification_status TEXT NOT NULL CHECK(verification_status IN (
        'VERIFIED','SUBMISSION_UNVERIFIED','FAILED_SAFELY','BLOCKED'
    )),
    success_evidence_json TEXT NOT NULL DEFAULT '{}',
    receipt_json TEXT NOT NULL,
    receipt_digest TEXT NOT NULL CHECK(length(receipt_digest) = 64),
    created_at TEXT NOT NULL,
    UNIQUE(application_id, plan_id, command_id),
    UNIQUE(receipt_digest)
);

CREATE TRIGGER IF NOT EXISTS verified_submission_receipt_immutable_update
BEFORE UPDATE ON application_submission_receipts
WHEN OLD.verification_status = 'VERIFIED'
BEGIN
    SELECT RAISE(ABORT, 'verified submission receipt is immutable');
END;

CREATE TRIGGER IF NOT EXISTS verified_submission_receipt_immutable_delete
BEFORE DELETE ON application_submission_receipts
WHEN OLD.verification_status = 'VERIFIED'
BEGIN
    SELECT RAISE(ABORT, 'verified submission receipt is immutable');
END;

CREATE TABLE IF NOT EXISTS application_mail_events (
    mail_event_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    message_id TEXT NOT NULL,
    thread_id TEXT,
    sender_domain TEXT,
    subject_digest TEXT NOT NULL CHECK(length(subject_digest) = 64),
    occurred_at TEXT NOT NULL,
    classification TEXT NOT NULL CHECK(classification IN (
        'APPLICATION_CONFIRMATION','ACCOUNT_VERIFICATION','OTP','ASSESSMENT',
        'RECRUITER_RESPONSE','INTERVIEW','REJECTION','OFFER','BACKGROUND_CHECK',
        'REFERENCE_REQUEST','OTHER'
    )),
    application_id TEXT REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    correlation_confidence REAL NOT NULL CHECK(correlation_confidence >= 0 AND correlation_confidence <= 1),
    duplicate_digest TEXT NOT NULL CHECK(length(duplicate_digest) = 64) UNIQUE,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_application_mail_events_application
ON application_mail_events(application_id, occurred_at DESC);
