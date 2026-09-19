-- Add bounded lifetime and explicit invalidation to encrypted hosted ATS sessions.

ALTER TABLE hosted_account_sessions ADD COLUMN expires_at TEXT;
ALTER TABLE hosted_account_sessions ADD COLUMN invalidated_at TEXT;
ALTER TABLE hosted_account_sessions ADD COLUMN invalidation_reason TEXT;

UPDATE hosted_account_sessions
SET expires_at = datetime(updated_at, '+7 days')
WHERE expires_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_hosted_account_sessions_expiry
    ON hosted_account_sessions(tenant_id,user_id,expires_at,invalidated_at);
