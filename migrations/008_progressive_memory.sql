CREATE TABLE progressive_memories (
    memory_id TEXT PRIMARY KEY,
    memory_kind TEXT NOT NULL
        CHECK (memory_kind IN ('SITE', 'QUESTION', 'FAILURE', 'SUCCESS', 'USER_CORRECTION', 'GLOBAL_PATTERN')),
    semantic_type TEXT,
    site_origin TEXT,
    component_fingerprint TEXT,
    question_fingerprint TEXT,
    interpretation_key TEXT,
    strategy_key TEXT,
    canonical_option_key TEXT,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    verified_successes INTEGER NOT NULL DEFAULT 0 CHECK (verified_successes >= 0),
    verified_failures INTEGER NOT NULL DEFAULT 0 CHECK (verified_failures >= 0),
    owner_corrections INTEGER NOT NULL DEFAULT 0 CHECK (owner_corrections >= 0),
    created_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    expires_at TEXT,
    version INTEGER NOT NULL CHECK (version >= 1),
    state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'SUPPRESSED', 'ROLLED_BACK')),
    CHECK (memory_kind <> 'SITE' OR site_origin IS NOT NULL),
    CHECK (memory_kind <> 'QUESTION' OR question_fingerprint IS NOT NULL),
    CHECK (
        memory_kind <> 'GLOBAL_PATTERN'
        OR (site_origin IS NULL AND question_fingerprint IS NULL)
    ),
    CHECK (
        memory_kind <> 'USER_CORRECTION'
        OR question_fingerprint IS NOT NULL
        OR interpretation_key IS NOT NULL
    )
);

CREATE INDEX idx_progressive_memories_site_semantic
ON progressive_memories(site_origin, semantic_type, state, confidence DESC);

CREATE INDEX idx_progressive_memories_component
ON progressive_memories(component_fingerprint, semantic_type, state, confidence DESC);

CREATE INDEX idx_progressive_memories_question
ON progressive_memories(question_fingerprint, semantic_type, state, confidence DESC);

CREATE INDEX idx_progressive_memories_observed
ON progressive_memories(state, last_observed_at DESC);

CREATE TABLE progressive_memory_observations (
    observation_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES progressive_memories(memory_id) ON DELETE CASCADE,
    occurred_at TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    owner_corrected INTEGER NOT NULL CHECK (owner_corrected IN (0, 1)),
    failure_class TEXT
);

CREATE INDEX idx_progressive_memory_observations_memory_time
ON progressive_memory_observations(memory_id, occurred_at DESC);
