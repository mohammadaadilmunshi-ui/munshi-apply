ALTER TABLE complete_application_prepare_jobs
ADD COLUMN continuation_count INTEGER NOT NULL DEFAULT 0
CHECK(continuation_count >= 0);

ALTER TABLE complete_application_prepare_jobs
ADD COLUMN continuation_pending INTEGER NOT NULL DEFAULT 0
CHECK(continuation_pending IN (0,1));

ALTER TABLE complete_application_prepare_jobs
ADD COLUMN continuation_in_flight INTEGER NOT NULL DEFAULT 0
CHECK(continuation_in_flight IN (0,1));

CREATE INDEX IF NOT EXISTS idx_complete_application_prepare_jobs_continuation
ON complete_application_prepare_jobs(state, continuation_pending, available_at);
