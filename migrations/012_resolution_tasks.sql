CREATE TABLE resolution_tasks (
    task_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    session_id TEXT,
    checkpoint_id TEXT,
    page_id TEXT,
    control_id TEXT,
    question_id TEXT,
    question TEXT,
    semantic_type TEXT,
    category TEXT NOT NULL
        CHECK (category IN (
            'MISSING_FACT',
            'AMBIGUOUS_QUESTION',
            'LOW_CONFIDENCE',
            'AUTHENTICATION',
            'EMAIL_VERIFICATION',
            'INTERACTION_FAILURE',
            'DOCUMENT_REQUIRED',
            'LEGAL_CONFIRMATION',
            'CAPTCHA',
            'EXTERNAL_ACTION',
            'TEMPORARY_FAILURE',
            'BLOCKING_CONFLICT'
        )),
    status TEXT NOT NULL
        CHECK (status IN (
            'PENDING',
            'RESOLVING',
            'WAITING_FOR_USER',
            'RESOLVED',
            'FAILED',
            'EXPIRED'
        )),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    auto_resolvable INTEGER NOT NULL CHECK (auto_resolvable IN (0, 1)),
    requires_user INTEGER NOT NULL CHECK (requires_user IN (0, 1)),
    grouping_scope TEXT NOT NULL
        CHECK (grouping_scope IN ('NONE', 'EXACT_QUESTION', 'SEMANTIC')),
    group_key TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    attempted_resolvers_json TEXT NOT NULL DEFAULT '[]',
    reason TEXT NOT NULL,
    resolution_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (grouping_scope = 'NONE' AND group_key IS NULL)
        OR (grouping_scope <> 'NONE' AND group_key IS NOT NULL)
    ),
    CHECK (
        (status = 'RESOLVED' AND resolution_json IS NOT NULL)
        OR (status <> 'RESOLVED' AND resolution_json IS NULL)
    )
);

CREATE INDEX idx_resolution_tasks_application_status
ON resolution_tasks(application_id, status, updated_at DESC);

CREATE INDEX idx_resolution_tasks_status_updated
ON resolution_tasks(status, updated_at DESC);

CREATE INDEX idx_resolution_tasks_group_status
ON resolution_tasks(group_key, status, updated_at DESC)
WHERE group_key IS NOT NULL;

CREATE INDEX idx_resolution_tasks_session_checkpoint
ON resolution_tasks(session_id, checkpoint_id)
WHERE session_id IS NOT NULL;
