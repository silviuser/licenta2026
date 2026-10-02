-- REWORK 2 (D27/D28): pooling becomes selective. A per-JD match records exactly
-- which other JDs it pulled applications from (source_jd_ids), replacing the
-- coarse include_other_applications flag as the source of truth. The legacy
-- boolean is kept read-only (non-destructive); new jobs still set it to
-- (source_jd_ids is non-empty) so HistoryPage keeps a truthful flag.
ALTER TABLE match_jobs ADD COLUMN source_jd_ids JSONB;

-- D30 dashboard: denormalise the top candidate score so per-JD aggregation is
-- pure SQL (no JSON parsing per position). Populated on success for new jobs.
ALTER TABLE match_jobs ADD COLUMN top_score DOUBLE PRECISION;

-- Backfill top_score for historical reports: candidates[0] is the top-ranked
-- SUCCEEDED candidate (the report sorts scored candidates by score desc before
-- appending failed ones). Null-scored heads (no succeeded candidate) are skipped.
UPDATE match_jobs
   SET top_score = (result_json -> 'candidates' -> 0 ->> 'overall_score')::double precision
 WHERE result_json IS NOT NULL
   AND result_json -> 'candidates' -> 0 ->> 'overall_score' IS NOT NULL;
