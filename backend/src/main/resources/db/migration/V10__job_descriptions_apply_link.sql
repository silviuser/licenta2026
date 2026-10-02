-- REWORK 3 (D32/D33): public candidate apply link per JD. The token is the
-- capability credential (a 256-bit random URL-safe string), not the JD id. Each
-- JD has at most one active token; regenerating overwrites this column so the old
-- token instantly stops resolving.
ALTER TABLE job_descriptions ADD COLUMN apply_token VARCHAR(64);
ALTER TABLE job_descriptions ADD COLUMN apply_link_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- Unique per token. Partial index tolerates the many JDs without a token
-- (apply_token IS NULL); Postgres would also allow multiple NULLs in a plain
-- unique index, but the partial form documents the intent and keeps it lean.
CREATE UNIQUE INDEX ux_jd_apply_token
    ON job_descriptions (apply_token)
    WHERE apply_token IS NOT NULL;
