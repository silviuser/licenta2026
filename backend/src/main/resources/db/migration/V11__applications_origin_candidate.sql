-- REWORK 3 (D37): an Application now records how it was created. Recruiter flows
-- (bulk upload, attach-from-library) stay RECRUITER; submissions through a public
-- apply link are CANDIDATE_LINK and carry the candidate's contact details.
ALTER TABLE applications ADD COLUMN origin VARCHAR(16) NOT NULL DEFAULT 'RECRUITER';
ALTER TABLE applications ADD CONSTRAINT chk_application_origin
    CHECK (origin IN ('RECRUITER', 'CANDIDATE_LINK'));

ALTER TABLE applications ADD COLUMN candidate_name  VARCHAR(255);
ALTER TABLE applications ADD COLUMN candidate_email VARCHAR(320);
ALTER TABLE applications ADD COLUMN candidate_phone VARCHAR(64);
-- When the candidate applied (their submission time). NULL on legacy/recruiter
-- rows, which fall back to created_at for display.
ALTER TABLE applications ADD COLUMN applied_at TIMESTAMPTZ;

-- Re-application dedup is on (jd_id, candidate_email): the same email applying
-- again to the same position replaces its CV (D36).
CREATE INDEX idx_applications_jd_email ON applications (jd_id, candidate_email);
