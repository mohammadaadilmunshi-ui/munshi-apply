CREATE TABLE profile_records (
    record_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
    kind TEXT NOT NULL
        CHECK (kind IN ('EDUCATION', 'EMPLOYMENT', 'PROJECT', 'CERTIFICATION', 'LANGUAGE')),
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_profile_records_profile_kind
ON profile_records(profile_id, kind, updated_at);

CREATE TABLE profile_record_facts (
    fact_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES profile_records(record_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    category TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    source TEXT NOT NULL,
    confirmed_at TEXT,
    updated_at TEXT NOT NULL,
    protected INTEGER NOT NULL CHECK (protected IN (0, 1)),
    UNIQUE(record_id, key)
);

CREATE INDEX idx_profile_record_facts_record_key
ON profile_record_facts(record_id, key);

CREATE TABLE evidence_nodes (
    evidence_id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id) ON DELETE CASCADE,
    kind TEXT NOT NULL
        CHECK (kind IN (
            'PROFILE_FACT', 'RESUME_BULLET', 'EMPLOYMENT', 'EDUCATION', 'PROJECT',
            'CERTIFICATION', 'JOB_REQUIREMENT', 'COMPANY_CONTEXT', 'USER_CONFIRMED_ANSWER'
        )),
    text TEXT NOT NULL,
    semantic_types_json TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    protected INTEGER NOT NULL CHECK (protected IN (0, 1)),
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_evidence_nodes_application_kind
ON evidence_nodes(application_id, kind, updated_at);

CREATE TABLE evidence_edges (
    from_evidence_id TEXT NOT NULL REFERENCES evidence_nodes(evidence_id) ON DELETE CASCADE,
    to_evidence_id TEXT NOT NULL REFERENCES evidence_nodes(evidence_id) ON DELETE CASCADE,
    relation TEXT NOT NULL
        CHECK (relation IN ('SUPPORTS', 'DERIVED_FROM', 'CONTRADICTS', 'DUPLICATES')),
    PRIMARY KEY (from_evidence_id, to_evidence_id, relation),
    CHECK (from_evidence_id <> to_evidence_id)
);

CREATE INDEX idx_evidence_edges_target_relation
ON evidence_edges(to_evidence_id, relation);

CREATE TABLE application_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    state TEXT NOT NULL,
    page_id TEXT,
    page_fingerprint TEXT NOT NULL,
    completed_control_ids_json TEXT NOT NULL,
    pending_control_ids_json TEXT NOT NULL,
    selected_resume_id TEXT,
    selected_resume_sha256 TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(application_id, sequence)
);

CREATE INDEX idx_application_checkpoints_latest
ON application_checkpoints(application_id, sequence DESC);

CREATE TABLE application_resume_selections (
    selection_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    resume_id TEXT NOT NULL REFERENCES resumes(resume_id),
    resume_sha256 TEXT NOT NULL,
    locked_at TEXT NOT NULL
);

CREATE INDEX idx_application_resume_selections_application
ON application_resume_selections(application_id, locked_at DESC);

CREATE TABLE ai_usage (
    usage_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    cost_usd REAL NOT NULL CHECK (cost_usd >= 0),
    correlation_id TEXT
);

CREATE INDEX idx_ai_usage_month_provider
ON ai_usage(occurred_at, provider, model);
