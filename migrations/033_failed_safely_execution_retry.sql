PRAGMA foreign_keys = OFF;

CREATE TABLE complete_application_sessions_v2 (
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
    updated_at TEXT NOT NULL
);

INSERT INTO complete_application_sessions_v2
SELECT * FROM complete_application_sessions;

DROP TABLE complete_application_sessions;
ALTER TABLE complete_application_sessions_v2 RENAME TO complete_application_sessions;

CREATE INDEX idx_complete_application_sessions_state
ON complete_application_sessions(state, updated_at DESC);

CREATE UNIQUE INDEX idx_complete_application_sessions_current_plan
ON complete_application_sessions(application_id, plan_id)
WHERE state <> 'FAILED_SAFELY';

PRAGMA foreign_keys = ON;
