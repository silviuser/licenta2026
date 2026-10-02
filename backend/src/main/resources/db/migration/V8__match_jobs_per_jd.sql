-- REWORK 1 (D23, D24): match becomes per-JD (1 job, N CV scorings). A per-JD job
-- has cv_id = NULL and stores the ranked candidate report in result_json.
ALTER TABLE match_jobs ALTER COLUMN cv_id DROP NOT NULL;
ALTER TABLE match_jobs ADD COLUMN include_other_applications BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE match_jobs ADD COLUMN candidate_count INTEGER;
