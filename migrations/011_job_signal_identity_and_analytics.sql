ALTER TABLE job_signal_reports
ADD COLUMN job_id TEXT REFERENCES jobs(job_id);

ALTER TABLE job_signal_reports
ADD COLUMN source_identity TEXT;

ALTER TABLE job_signal_evidence
ADD COLUMN direction TEXT NOT NULL DEFAULT 'CONCERN'
    CHECK (direction IN ('POSITIVE', 'CONCERN', 'NEUTRAL'));

ALTER TABLE job_signal_evidence
ADD COLUMN source TEXT NOT NULL DEFAULT 'JOB_POSTING'
    CHECK (source IN ('JOB_POSTING', 'APPLICATION_OBSERVATION'));

UPDATE job_signal_evidence
SET direction = CASE
    WHEN dimension IN ('COMPENSATION_CLARITY', 'SENIORITY_ALIGNMENT', 'ROLE_STABILITY')
         AND (
             SELECT score
             FROM job_signal_dimensions
             WHERE job_signal_dimensions.report_id = job_signal_evidence.report_id
               AND job_signal_dimensions.dimension = job_signal_evidence.dimension
         ) >= 68 THEN 'POSITIVE'
    WHEN dimension IN ('COMPENSATION_CLARITY', 'SENIORITY_ALIGNMENT', 'ROLE_STABILITY')
         AND (
             SELECT score
             FROM job_signal_dimensions
             WHERE job_signal_dimensions.report_id = job_signal_evidence.report_id
               AND job_signal_dimensions.dimension = job_signal_evidence.dimension
         ) <= 35 THEN 'CONCERN'
    WHEN dimension NOT IN ('COMPENSATION_CLARITY', 'SENIORITY_ALIGNMENT', 'ROLE_STABILITY')
         AND (
             SELECT score
             FROM job_signal_dimensions
             WHERE job_signal_dimensions.report_id = job_signal_evidence.report_id
               AND job_signal_dimensions.dimension = job_signal_evidence.dimension
         ) <= 30 THEN 'POSITIVE'
    WHEN dimension NOT IN ('COMPENSATION_CLARITY', 'SENIORITY_ALIGNMENT', 'ROLE_STABILITY')
         AND (
             SELECT score
             FROM job_signal_dimensions
             WHERE job_signal_dimensions.report_id = job_signal_evidence.report_id
               AND job_signal_dimensions.dimension = job_signal_evidence.dimension
         ) >= 65 THEN 'CONCERN'
    ELSE 'NEUTRAL'
END;

INSERT OR IGNORE INTO jobs (
    job_id,
    company,
    role,
    requisition_id,
    job_url,
    application_url,
    location,
    work_arrangement,
    employment_type,
    compensation,
    description,
    created_at,
    updated_at
)
SELECT
    'job-legacy-' || application_id,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    MIN(created_at),
    MAX(updated_at)
FROM job_signal_reports
WHERE job_id IS NULL
GROUP BY application_id;

UPDATE job_signal_reports
SET
    job_id = 'job-legacy-' || application_id,
    source_identity = 'legacy:' || source_fingerprint
WHERE job_id IS NULL OR source_identity IS NULL;

UPDATE applications
SET job_id = (
    SELECT reports.job_id
    FROM job_signal_reports AS reports
    WHERE reports.application_id = applications.application_id
    ORDER BY reports.evaluated_at DESC, reports.report_id DESC
    LIMIT 1
)
WHERE job_id IS NULL
  AND EXISTS (
    SELECT 1
    FROM job_signal_reports AS reports
    WHERE reports.application_id = applications.application_id
  );

CREATE INDEX idx_job_signal_reports_job_source_evaluated
ON job_signal_reports(job_id, source_identity, evaluated_at DESC);

CREATE UNIQUE INDEX idx_job_signal_reports_application_job_source_fingerprint
ON job_signal_reports(application_id, job_id, source_identity, source_fingerprint);
