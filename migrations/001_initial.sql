CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    category TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    source TEXT NOT NULL,
    confirmed_at TEXT,
    updated_at TEXT NOT NULL,
    protected INTEGER NOT NULL CHECK (protected IN (0, 1)),
    UNIQUE(profile_id, key)
);

CREATE TABLE IF NOT EXISTS resumes (
    resume_id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    version INTEGER NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    source_path TEXT NOT NULL,
    role_family TEXT,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    company TEXT,
    role TEXT,
    requisition_id TEXT,
    job_url TEXT,
    application_url TEXT,
    location TEXT,
    work_arrangement TEXT,
    employment_type TEXT,
    compensation TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    job_id TEXT REFERENCES jobs(job_id),
    status TEXT NOT NULL,
    resume_id TEXT REFERENCES resumes(resume_id),
    job_signal_score REAL,
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_pages (
    page_id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT,
    state TEXT,
    snapshot_json TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id) ON DELETE CASCADE,
    page_id TEXT REFERENCES application_pages(page_id) ON DELETE CASCADE,
    control_id TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    sensitive INTEGER NOT NULL CHECK (sensitive IN (0, 1)),
    requires_review INTEGER NOT NULL CHECK (requires_review IN (0, 1))
);

CREATE TABLE IF NOT EXISTS answers (
    answer_id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
    value_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    approved_at TEXT,
    submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS interaction_attempts (
    attempt_id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id) ON DELETE CASCADE,
    control_id TEXT NOT NULL,
    recipe_id TEXT,
    level INTEGER NOT NULL,
    result TEXT NOT NULL,
    verification_json TEXT,
    attempted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_events (
    learning_event_id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id),
    scope TEXT NOT NULL,
    event_type TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_events (
    event_id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_application_events_application_time
ON application_events(application_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_questions_application_semantic
ON questions(application_id, semantic_type);
