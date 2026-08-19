ALTER TABLE profile_records
ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0);

CREATE INDEX idx_profile_records_profile_kind_order
ON profile_records(profile_id, kind, sort_order, record_id);

CREATE TABLE profile_record_tombstones (
    record_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
    kind TEXT NOT NULL
        CHECK (kind IN ('EDUCATION', 'EMPLOYMENT', 'PROJECT', 'CERTIFICATION', 'LANGUAGE')),
    deleted_at TEXT NOT NULL,
    confirmed INTEGER NOT NULL CHECK (confirmed = 1)
);

CREATE INDEX idx_profile_record_tombstones_profile_deleted
ON profile_record_tombstones(profile_id, deleted_at, record_id);
