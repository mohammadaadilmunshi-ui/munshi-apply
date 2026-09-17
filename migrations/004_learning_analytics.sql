CREATE TABLE interaction_recipes (
    recipe_id TEXT PRIMARY KEY,
    component_fingerprint TEXT NOT NULL,
    semantic_type TEXT,
    site_origin TEXT,
    actions_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    state TEXT NOT NULL CHECK (state IN ('SHADOW', 'PROMOTED', 'ROLLED_BACK')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(component_fingerprint, semantic_type, site_origin, version)
);

CREATE INDEX idx_interaction_recipes_lookup
ON interaction_recipes(component_fingerprint, site_origin, state, version DESC);

CREATE TABLE recipe_attempts (
    attempt_id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL REFERENCES interaction_recipes(recipe_id) ON DELETE CASCADE,
    application_id TEXT REFERENCES applications(application_id) ON DELETE SET NULL,
    occurred_at TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    failure_reason TEXT
);

CREATE INDEX idx_recipe_attempts_recipe_time
ON recipe_attempts(recipe_id, occurred_at DESC);

CREATE TABLE application_outcomes (
    outcome_event_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    stage TEXT NOT NULL
        CHECK (stage IN ('APPLIED', 'ASSESSMENT', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN')),
    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL
);

CREATE INDEX idx_application_outcomes_application_time
ON application_outcomes(application_id, occurred_at DESC);

CREATE TABLE attribution_tokens (
    token TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE UNIQUE INDEX idx_attribution_tokens_active_application
ON attribution_tokens(application_id)
WHERE revoked_at IS NULL;

CREATE TABLE experiments (
    experiment_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    minimum_sample_per_variant INTEGER NOT NULL CHECK (minimum_sample_per_variant >= 1),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'PAUSED', 'COMPLETE')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE experiment_variants (
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    variant_id TEXT NOT NULL,
    label TEXT NOT NULL,
    weight REAL NOT NULL CHECK (weight > 0),
    PRIMARY KEY (experiment_id, variant_id)
);

CREATE TABLE experiment_assignments (
    experiment_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (experiment_id, subject_id),
    FOREIGN KEY (experiment_id, variant_id)
        REFERENCES experiment_variants(experiment_id, variant_id) ON DELETE CASCADE
);

CREATE INDEX idx_experiment_assignments_variant
ON experiment_assignments(experiment_id, variant_id, assigned_at);
