-- REWORK 4 (D42): an email address associated with each CV.
--   extracted_email — from the NLP contact.primary_email, populated at
--                     extraction time and by the startup backfill (D46).
--   manual_email    — the recruiter's correction; takes precedence over
--                     the extracted value (D45). Clearing it reverts to extracted.
-- VARCHAR(320) = RFC max address length, consistent with applications.candidate_email (V11).
ALTER TABLE cvs ADD COLUMN extracted_email VARCHAR(320);
ALTER TABLE cvs ADD COLUMN manual_email    VARCHAR(320);
