CREATE TABLE cvs (
    id                   UUID PRIMARY KEY,
    owner_id             UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    original_filename    VARCHAR(512) NOT NULL,
    content_type         VARCHAR(128) NOT NULL,
    size_bytes           BIGINT       NOT NULL,
    pdf_data             BYTEA        NOT NULL,
    detected_language    VARCHAR(8),
    extracted_candidates JSONB,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_cvs_owner ON cvs (owner_id);
