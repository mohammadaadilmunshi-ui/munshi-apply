CREATE TABLE IF NOT EXISTS complete_application_prepare_jobs (
    job_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    application_id TEXT NOT NULL
        REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN (
        'QUEUED','RUNNING','WAITING_INPUT','READY_FOR_REVIEW',
        'BLOCKED','FAILED_SAFELY','CANCELLED'
    )),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 10),
    available_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    cancel_requested_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    CHECK(
        (state = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR state <> 'RUNNING'
    )
);

CREATE INDEX IF NOT EXISTS idx_complete_application_prepare_jobs_claim
ON complete_application_prepare_jobs(state, available_at, created_at, job_id);

CREATE INDEX IF NOT EXISTS idx_complete_application_prepare_jobs_owner
ON complete_application_prepare_jobs(tenant_id, user_id, application_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_complete_application_prepare_jobs_lease
ON complete_application_prepare_jobs(state, lease_expires_at)
WHERE state = 'RUNNING';
