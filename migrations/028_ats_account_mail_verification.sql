-- Durable ATS account lifecycle and mail-verification coordination.
-- Secrets, OTPs, reset tokens, magic-link tokens, and raw verification URLs
-- MUST NOT be stored in these tables. Only opaque credential references and
-- verification artifact digests/metadata are durable.

CREATE TABLE IF NOT EXISTS ats_account_state (
    account_id TEXT PRIMARY KEY REFERENCES account_records(account_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    credential_ref TEXT,
    mail_alias TEXT,
    state TEXT NOT NULL CHECK (state IN (
        'UNPROVISIONED',
        'CREATING',
        'VERIFICATION_PENDING',
        'VERIFIED',
        'AUTHENTICATED',
        'NEEDS_USER_ACTION',
        'BLOCKED',
        'FAILED_SAFE'
    )),
    verified_at TEXT,
    authenticated_at TEXT,
    issue_code TEXT,
    issue_detail TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ats_account_state_provider
    ON ats_account_state(provider, state);
CREATE INDEX IF NOT EXISTS idx_ats_account_state_mail_alias
    ON ats_account_state(mail_alias);

CREATE TABLE IF NOT EXISTS ats_account_continuations (
    continuation_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account_records(account_id) ON DELETE CASCADE,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    execution_session_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    target_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'PENDING', 'READY', 'CONSUMED', 'CANCELLED', 'ISSUE'
    )),
    issue_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, application_id, execution_session_id)
);

CREATE INDEX IF NOT EXISTS idx_ats_account_continuations_application
    ON ats_account_continuations(application_id, state);

CREATE TABLE IF NOT EXISTS ats_verification_challenges (
    challenge_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account_records(account_id) ON DELETE CASCADE,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    continuation_id TEXT NOT NULL REFERENCES ats_account_continuations(continuation_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN (
        'EMAIL_LINK',
        'EMAIL_CODE',
        'PASSWORD_RESET_LINK',
        'MAGIC_LOGIN_LINK'
    )),
    state TEXT NOT NULL CHECK (state IN (
        'PENDING', 'READY', 'CLAIMED', 'CONSUMED', 'EXPIRED', 'ISSUE'
    )),
    mail_event_id TEXT,
    artifact_digest TEXT,
    created_at TEXT NOT NULL,
    available_at TEXT,
    claimed_at TEXT,
    consumed_at TEXT,
    expires_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ats_verification_mail_event_once
    ON ats_verification_challenges(mail_event_id)
    WHERE mail_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ats_verification_pending
    ON ats_verification_challenges(account_id, state, created_at);

CREATE TABLE IF NOT EXISTS ats_account_events (
    event_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account_records(account_id) ON DELETE CASCADE,
    application_id TEXT REFERENCES applications(application_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'ATS_ACCOUNT_CREATED',
        'ATS_ACCOUNT_VERIFICATION_PENDING',
        'ATS_ACCOUNT_VERIFIED',
        'ATS_ACCOUNT_AUTHENTICATED',
        'ATS_ACCOUNT_ISSUE'
    )),
    occurred_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ats_account_events_account
    ON ats_account_events(account_id, occurred_at);
