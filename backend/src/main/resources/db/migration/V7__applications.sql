-- REWORK 1 (D20): Application = CV ↔ JD link (per recruiter). A CV exists once;
-- applying it to a JD is an edge. Unique (cv_id, jd_id) makes attaching idempotent.
CREATE TABLE applications (
    id         UUID PRIMARY KEY,
    owner_id   UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    cv_id      UUID NOT NULL REFERENCES cvs (id) ON DELETE CASCADE,
    jd_id      UUID NOT NULL REFERENCES job_descriptions (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_application UNIQUE (cv_id, jd_id)
);

CREATE INDEX idx_applications_jd ON applications (jd_id);
CREATE INDEX idx_applications_owner ON applications (owner_id);
