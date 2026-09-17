PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ai_drafts (
    draft_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    page_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    control_id TEXT NOT NULL,
    question_fingerprint TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    response_id TEXT NOT NULL,
    original_text TEXT NOT NULL,
    current_text TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'APPROVED', 'REJECTED', 'SUPERSEDED', 'USED')),
    evidence_ids_json TEXT NOT NULL,
    claims_json TEXT NOT NULL,
    usage_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_drafts_application_page
ON ai_drafts(application_id, page_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_drafts_question_binding
ON ai_drafts(application_id, question_id, control_id, generated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_drafts_one_approved_binding
ON ai_drafts(application_id, question_id, control_id)
WHERE status = 'APPROVED';
