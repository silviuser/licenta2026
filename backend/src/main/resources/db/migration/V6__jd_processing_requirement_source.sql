-- REWORK 1 (D18, D26): JD background extraction status + requirement provenance.
ALTER TABLE job_descriptions ADD COLUMN processing_status VARCHAR(16) NOT NULL DEFAULT 'READY';
ALTER TABLE job_descriptions ADD COLUMN processing_error TEXT;

ALTER TABLE job_descriptions ADD CONSTRAINT chk_jd_proc_status
    CHECK (processing_status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED'));

-- EXTRACTED = produced by /v1/extract-jd; MANUAL = entered/edited by the recruiter.
-- Legacy requirements default to MANUAL (they were all hand-entered under D7).
ALTER TABLE requirements ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'MANUAL';

ALTER TABLE requirements ADD CONSTRAINT chk_req_source
    CHECK (source IN ('EXTRACTED', 'MANUAL'));
