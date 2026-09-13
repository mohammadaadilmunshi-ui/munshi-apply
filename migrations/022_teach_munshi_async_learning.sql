CREATE TABLE IF NOT EXISTS teach_munshi_lessons (
    lesson_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    application_id TEXT REFERENCES applications(application_id) ON DELETE SET NULL,
    site_origin TEXT NOT NULL,
    component_fingerprint TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    ats_family TEXT,
    tenant_key TEXT,
    ui_fingerprint TEXT,
    question_fingerprint TEXT,
    teacher_kind TEXT NOT NULL CHECK (
        teacher_kind IN (
            'MODEL',
            'LOCAL_MODEL',
            'DETERMINISTIC_RECOVERY',
            'USER_DEMONSTRATION',
            'EXISTING_RECIPE'
        )
    ),
    teacher_provider TEXT,
    source_lane TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        state IN ('PENDING','PROCESSING','LEARNED','SKIPPED','FAILED')
    ),
    recipe_id TEXT REFERENCES interaction_recipes(recipe_id) ON DELETE SET NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_teach_munshi_lessons_queue
ON teach_munshi_lessons(state, created_at, lesson_id);

CREATE INDEX IF NOT EXISTS idx_teach_munshi_lessons_context
ON teach_munshi_lessons(
    site_origin,
    component_fingerprint,
    semantic_type,
    state,
    created_at DESC
);

CREATE INDEX IF NOT EXISTS idx_teach_munshi_lessons_provider
ON teach_munshi_lessons(teacher_provider, state, created_at DESC);
