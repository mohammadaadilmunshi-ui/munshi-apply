-- Separate resumable semantic continuations from mechanical retry attempts.
-- A plan supersession / resolved checkpoint must not consume the browser crash budget.

ALTER TABLE complete_application_prepare_jobs
ADD COLUMN continuation_count INTEGER NOT NULL DEFAULT 0
CHECK(continuation_count >= 0);

ALTER TABLE complete_application_prepare_jobs
ADD COLUMN continuation_pending INTEGER NOT NULL DEFAULT 0
CHECK(continuation_pending IN (0,1));
