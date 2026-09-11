CREATE TABLE IF NOT EXISTS complete_application_trust_checkpoints (
    trust_checkpoint_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    prepare_job_id TEXT NOT NULL
        REFERENCES complete_application_prepare_jobs(job_id) ON DELETE RESTRICT,
    application_id TEXT NOT NULL
        REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    checkpoint_kind TEXT NOT NULL CHECK(checkpoint_kind IN (
        'AUTHENTICATION','CAPTCHA','MFA','OTP','IDENTITY_VERIFICATION'
    )),
    status TEXT NOT NULL CHECK(status IN (
        'WAITING_FOR_USER_AUTH','CLEARED','INVALIDATED'
    )),
    origin TEXT NOT NULL,
    path_sha256 TEXT NOT NULL CHECK(length(path_sha256) = 64),
    page_fingerprint_sha256 TEXT NOT NULL CHECK(length(page_fingerprint_sha256) = 64),
    observed_at TEXT NOT NULL,
    cleared_at TEXT,
    invalidated_at TEXT,
    updated_at TEXT NOT NULL,
    CHECK(
        (status = 'WAITING_FOR_USER_AUTH'
            AND cleared_at IS NULL AND invalidated_at IS NULL)
        OR
        (status = 'CLEARED'
            AND cleared_at IS NOT NULL AND invalidated_at IS NULL)
        OR
        (status = 'INVALIDATED'
            AND invalidated_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_complete_application_trust_checkpoint_active
ON complete_application_trust_checkpoints(session_id)
WHERE status = 'WAITING_FOR_USER_AUTH';

CREATE INDEX IF NOT EXISTS idx_complete_application_trust_checkpoint_job
ON complete_application_trust_checkpoints(
    tenant_id,user_id,prepare_job_id,observed_at DESC
);

CREATE TABLE IF NOT EXISTS complete_application_trust_checkpoint_events (
    event_id TEXT PRIMARY KEY,
    trust_checkpoint_id TEXT NOT NULL
        REFERENCES complete_application_trust_checkpoints(trust_checkpoint_id)
        ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'OBSERVED','WAITING_RECORDED','CLEARED','INVALIDATED'
    )),
    evidence_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_complete_application_trust_checkpoint_events_chain
ON complete_application_trust_checkpoint_events(
    trust_checkpoint_id,occurred_at,event_id
);

CREATE TRIGGER IF NOT EXISTS trust_checkpoint_events_immutable_update
BEFORE UPDATE ON complete_application_trust_checkpoint_events
BEGIN
    SELECT RAISE(ABORT, 'trust checkpoint event is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trust_checkpoint_events_immutable_delete
BEFORE DELETE ON complete_application_trust_checkpoint_events
BEGIN
    SELECT RAISE(ABORT, 'trust checkpoint event is immutable');
END;
