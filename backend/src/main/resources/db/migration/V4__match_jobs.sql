CREATE TABLE match_jobs (
    id                    UUID PRIMARY KEY,
    owner_id              UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    cv_id                 UUID NOT NULL REFERENCES cvs (id) ON DELETE CASCADE,
    jd_id                 UUID NOT NULL REFERENCES job_descriptions (id) ON DELETE CASCADE,
    status                VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at            TIMESTAMPTZ,
    finished_at           TIMESTAMPTZ,
    error_code            VARCHAR(128),
    error_detail          TEXT,
    overall_score         DOUBLE PRECISION,
    overall_class         VARCHAR(32),
    required_coverage     DOUBLE PRECISION,
    nice_to_have_coverage DOUBLE PRECISION,
    result_json           JSONB,
    pipeline_version      VARCHAR(256),
    CONSTRAINT chk_job_status CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'))
);

CREATE INDEX idx_match_jobs_owner_status ON match_jobs (owner_id, status);
CREATE INDEX idx_match_jobs_cv ON match_jobs (cv_id);
CREATE INDEX idx_match_jobs_jd ON match_jobs (jd_id);
