-- Encrypted hosted Chromium account-session persistence.
-- Browser cookies/local storage are encrypted with a key derived from the
-- authenticated Hunter-Apply execution bridge secret. No raw session token is
-- permitted in SQLite.

CREATE TABLE IF NOT EXISTS hosted_account_sessions (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    account_id TEXT,
    ciphertext BLOB NOT NULL,
    nonce BLOB NOT NULL,
    algorithm TEXT NOT NULL,
    state_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id, scope_key)
);

CREATE INDEX IF NOT EXISTS idx_hosted_account_sessions_account
    ON hosted_account_sessions(account_id, updated_at);
