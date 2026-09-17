CREATE TABLE IF NOT EXISTS ats_teach_lessons (
    lesson_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    application_id TEXT REFERENCES applications(application_id) ON DELETE SET NULL,
    site_origin TEXT NOT NULL,
    component_fingerprint TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    ats_family TEXT,
    tenant_key TEXT,
    ui_fingerprint TEXT,
    actions_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING','PROCESSING','LEARNED','SKIPPED','FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    recipe_id TEXT REFERENCES interaction_recipes(recipe_id) ON DELETE SET NULL,
    failure_reason TEXT,
    claimed_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ats_teach_lessons_queue
    ON ats_teach_lessons(state, created_at, lesson_id);
