-- Email evidence is secondary. It never authorizes or independently verifies submission.
CREATE TABLE IF NOT EXISTS confirmation_email_evidence (
    evidence_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    mailbox_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    receipt_id TEXT NOT NULL REFERENCES application_submission_receipts(receipt_id) ON DELETE RESTRICT,
    message_digest TEXT NOT NULL CHECK(length(message_digest)=64),
    evidence_digest TEXT NOT NULL CHECK(length(evidence_digest)=64),
    received_at TEXT NOT NULL,
    UNIQUE(tenant_id,user_id,mailbox_id,message_id)
);
CREATE TRIGGER IF NOT EXISTS confirmation_email_evidence_no_update
BEFORE UPDATE ON confirmation_email_evidence
BEGIN
    SELECT RAISE(ABORT, 'confirmation email evidence is immutable');
END;
CREATE TRIGGER IF NOT EXISTS confirmation_email_evidence_no_delete
BEFORE DELETE ON confirmation_email_evidence
BEGIN
    SELECT RAISE(ABORT, 'confirmation email evidence is immutable');
END;
