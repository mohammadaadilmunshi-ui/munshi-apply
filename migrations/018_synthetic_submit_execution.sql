CREATE TABLE IF NOT EXISTS synthetic_submit_executions (
    command_id TEXT PRIMARY KEY
        REFERENCES synthetic_submit_command_inbox(command_id) ON DELETE RESTRICT,
    application_id TEXT NOT NULL
        REFERENCES applications(application_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    session_id TEXT NOT NULL
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK(provider = 'GREENHOUSE'),
    state TEXT NOT NULL CHECK(state IN (
        'SUBMITTING','SUBMITTED','SUBMISSION_UNVERIFIED','BLOCKED','FAILED_SAFELY'
    )),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    action_executed INTEGER CHECK(action_executed IS NULL OR action_executed IN (0,1)),
    submission_url TEXT,
    provider_application_id TEXT,
    response_status INTEGER,
    submit_action TEXT,
    submit_method TEXT,
    success_evidence_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    result_digest TEXT CHECK(result_digest IS NULL OR length(result_digest) = 64),
    UNIQUE(session_id)
);

CREATE INDEX IF NOT EXISTS idx_synthetic_submit_executions_state
ON synthetic_submit_executions(state, started_at DESC);

CREATE TRIGGER IF NOT EXISTS synthetic_submit_executions_terminal_immutable_update
BEFORE UPDATE ON synthetic_submit_executions
WHEN OLD.state <> 'SUBMITTING'
BEGIN
    SELECT RAISE(ABORT, 'terminal synthetic submit execution is immutable');
END;

CREATE TRIGGER IF NOT EXISTS synthetic_submit_executions_immutable_delete
BEFORE DELETE ON synthetic_submit_executions
BEGIN
    SELECT RAISE(ABORT, 'synthetic submit execution is immutable');
END;
