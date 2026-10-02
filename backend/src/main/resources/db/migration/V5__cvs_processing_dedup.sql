-- REWORK 1 (D17, D22, D26): CV background processing + SHA-256 dedup.
ALTER TABLE cvs ADD COLUMN content_hash VARCHAR(64);
ALTER TABLE cvs ADD COLUMN processing_status VARCHAR(16) NOT NULL DEFAULT 'PENDING';
ALTER TABLE cvs ADD COLUMN processing_error TEXT;

ALTER TABLE cvs ADD CONSTRAINT chk_cv_proc_status
    CHECK (processing_status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED'));

-- CVs already carrying a cached ExtractResponse are READY; the rest stay PENDING.
UPDATE cvs SET processing_status = 'READY' WHERE extracted_candidates IS NOT NULL;

-- Per-owner content dedup (D22). Partial index tolerates legacy rows whose hash
-- was never computed (content_hash IS NULL); new uploads always carry a hash.
CREATE UNIQUE INDEX ux_cvs_owner_hash
    ON cvs (owner_id, content_hash)
    WHERE content_hash IS NOT NULL;
