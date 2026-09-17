CREATE TABLE IF NOT EXISTS job_signal_reports (
    report_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    overall_signal TEXT NOT NULL CHECK (
        overall_signal IN ('LOW', 'MODERATE', 'HIGH', 'INSUFFICIENT_DATA')
    ),
    overall_score INTEGER CHECK (
        overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)
    ),
    source_fingerprint TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(application_id, source_fingerprint)
);

CREATE TABLE IF NOT EXISTS job_signal_dimensions (
    report_id TEXT NOT NULL REFERENCES job_signal_reports(report_id) ON DELETE CASCADE,
    dimension TEXT NOT NULL,
    score INTEGER CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    PRIMARY KEY (report_id, dimension)
);

CREATE TABLE IF NOT EXISTS job_signal_evidence (
    signal_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES job_signal_reports(report_id) ON DELETE CASCADE,
    dimension TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MODERATE', 'HIGH')),
    evidence TEXT NOT NULL,
    explanation TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_signal_reports_application_evaluated
ON job_signal_reports(application_id, evaluated_at DESC);

CREATE INDEX IF NOT EXISTS idx_job_signal_dimensions_report
ON job_signal_dimensions(report_id, dimension);

CREATE INDEX IF NOT EXISTS idx_job_signal_evidence_report_dimension
ON job_signal_evidence(report_id, dimension, signal_id);
