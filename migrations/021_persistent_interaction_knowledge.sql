CREATE TABLE IF NOT EXISTS interaction_recipe_context (
    recipe_id TEXT PRIMARY KEY
        REFERENCES interaction_recipes(recipe_id) ON DELETE CASCADE,
    ats_family TEXT,
    tenant_key TEXT,
    ui_fingerprint TEXT,
    question_fingerprint TEXT,
    confidence REAL NOT NULL DEFAULT 0.50
        CHECK (confidence >= 0 AND confidence <= 1),
    verified_successes INTEGER NOT NULL DEFAULT 0
        CHECK (verified_successes >= 0),
    verified_failures INTEGER NOT NULL DEFAULT 0
        CHECK (verified_failures >= 0),
    consecutive_failures INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_failures >= 0),
    lifecycle_state TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (lifecycle_state IN ('ACTIVE', 'QUARANTINED')),
    last_used_at TEXT,
    last_verified_at TEXT,
    quarantined_at TEXT,
    quarantine_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interaction_recipe_context_lookup
ON interaction_recipe_context(
    ats_family,
    tenant_key,
    ui_fingerprint,
    question_fingerprint,
    lifecycle_state,
    confidence DESC
);

CREATE INDEX IF NOT EXISTS idx_interaction_recipe_context_health
ON interaction_recipe_context(lifecycle_state, consecutive_failures, last_verified_at DESC);

CREATE TABLE IF NOT EXISTS interaction_resolution_events (
    event_id TEXT PRIMARY KEY,
    application_id TEXT,
    site_origin TEXT NOT NULL,
    component_fingerprint TEXT,
    semantic_type TEXT,
    recipe_id TEXT REFERENCES interaction_recipes(recipe_id) ON DELETE SET NULL,
    resolution_lane TEXT NOT NULL CHECK (
        resolution_lane IN (
            'PROMOTED_RECIPE',
            'SHADOW_RECIPE',
            'NATIVE_CONTROL',
            'ARIA_PATTERN',
            'KEYBOARD_PATTERN',
            'STRUCTURAL_POPUP',
            'STATE_TRANSITION',
            'LOCAL_SEMANTIC_HINT',
            'CLAUDE_RECIPE_PROPOSAL',
            'VISUAL_ASSISTED_CONTROL'
        )
    ),
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    ai_provider TEXT,
    ai_model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    ai_cost_usd REAL NOT NULL DEFAULT 0 CHECK (ai_cost_usd >= 0),
    fallback_reason TEXT,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interaction_resolution_events_time
ON interaction_resolution_events(occurred_at DESC, resolution_lane);

CREATE INDEX IF NOT EXISTS idx_interaction_resolution_events_application
ON interaction_resolution_events(application_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_interaction_resolution_events_recipe
ON interaction_resolution_events(recipe_id, occurred_at DESC);
