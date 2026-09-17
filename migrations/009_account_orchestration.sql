CREATE TABLE IF NOT EXISTS account_records (
    account_id TEXT PRIMARY KEY,
    employer TEXT,
    scope_key TEXT NOT NULL,
    domain TEXT NOT NULL,
    portal_url TEXT NOT NULL,
    email TEXT NOT NULL,
    exists_flag INTEGER NOT NULL CHECK (exists_flag IN (0, 1)),
    created_at TEXT NOT NULL,
    last_used TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(scope_key, email)
);

CREATE TABLE IF NOT EXISTS account_application_links (
    account_id TEXT NOT NULL REFERENCES account_records(account_id) ON DELETE CASCADE,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (account_id, application_id)
);

CREATE INDEX IF NOT EXISTS idx_account_records_scope_email
ON account_records(scope_key, email);

CREATE INDEX IF NOT EXISTS idx_account_records_domain_last_used
ON account_records(domain, last_used DESC);

CREATE INDEX IF NOT EXISTS idx_account_application_links_application
ON account_application_links(application_id, linked_at DESC);
