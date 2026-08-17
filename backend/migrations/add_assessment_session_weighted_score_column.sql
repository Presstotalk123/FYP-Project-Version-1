-- Persist the weighted score at finalization instead of recomputing it on every read.
-- NULL = not yet finalized, or the assessment carries no weightage (matches
-- compute_weighted_score's None contract). Additive; existing sessions default to NULL
-- and are backfilled by backfill_assessment_session_weighted_scores.py.
--
-- Postgres-only: SQLite dev needs no migration (Base.metadata.create_all() adds the
-- column on startup).
ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS weighted_score DOUBLE PRECISION;
