CREATE TABLE IF NOT EXISTS career_os_application_plan_supersessions (
    replacement_plan_id TEXT PRIMARY KEY
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    prior_plan_id TEXT NOT NULL UNIQUE
        REFERENCES career_os_application_plans(plan_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    application_id TEXT NOT NULL,
    session_id TEXT NOT NULL
        REFERENCES complete_application_sessions(session_id) ON DELETE RESTRICT,
    prepare_job_id TEXT NOT NULL
        REFERENCES complete_application_prepare_jobs(job_id) ON DELETE RESTRICT,
    prior_plan_digest TEXT NOT NULL CHECK(length(prior_plan_digest) = 64),
    replacement_plan_digest TEXT NOT NULL CHECK(length(replacement_plan_digest) = 64),
    resolution_digest TEXT NOT NULL CHECK(length(resolution_digest) = 64),
    browser_form_digest TEXT NOT NULL CHECK(length(browser_form_digest) = 64),
    checkpoint_id TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    CHECK(prior_plan_id <> replacement_plan_id)
);

CREATE INDEX IF NOT EXISTS idx_application_plan_supersessions_owner_application
ON career_os_application_plan_supersessions(
    tenant_id, user_id, application_id, accepted_at DESC
);

CREATE TRIGGER IF NOT EXISTS application_plan_supersession_immutable_update
BEFORE UPDATE ON career_os_application_plan_supersessions
BEGIN
    SELECT RAISE(ABORT, 'application plan supersession is immutable');
END;

CREATE TRIGGER IF NOT EXISTS application_plan_supersession_immutable_delete
BEFORE DELETE ON career_os_application_plan_supersessions
BEGIN
    SELECT RAISE(ABORT, 'application plan supersession is immutable');
END;
