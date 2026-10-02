CREATE TABLE job_descriptions (
    id               UUID PRIMARY KEY,
    owner_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title            VARCHAR(512) NOT NULL,
    description_text TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_jds_owner ON job_descriptions (owner_id);

CREATE TABLE requirements (
    id          UUID PRIMARY KEY,
    jd_id       UUID NOT NULL REFERENCES job_descriptions (id) ON DELETE CASCADE,
    text        VARCHAR(2048) NOT NULL,
    skill_uri   VARCHAR(512),
    skill_label VARCHAR(512),
    importance  VARCHAR(32)  NOT NULL,
    confidence  DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    sort_order  INTEGER      NOT NULL DEFAULT 0,
    CONSTRAINT chk_req_importance CHECK (importance IN ('required', 'nice_to_have')),
    CONSTRAINT chk_req_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_requirements_jd ON requirements (jd_id);
