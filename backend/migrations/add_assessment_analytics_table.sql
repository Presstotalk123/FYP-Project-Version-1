-- Migration: Add assessment_analytics table — materialized cohort/class-group averages.
-- One row per (assessment_id, class_group); class_group NULL = the whole cohort. `payload`
-- holds the JSON-serialized RosterAnalytics (per-item/per-task breakdown + per-student
-- weighted totals) so every report reads the shared result instead of recomputing. `version`
-- is the ASSESSMENT_ANALYTICS cache-namespace generation at materialization time — a row whose
-- version lags the current namespace version is stale and gets recomputed on next read.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS assessment_analytics (
    id                  SERIAL PRIMARY KEY,
    assessment_id       INTEGER NOT NULL REFERENCES assessments(id),
    class_group         VARCHAR(255),
    student_count       INTEGER NOT NULL DEFAULT 0,
    avg_weighted_score  DOUBLE PRECISION,
    payload             TEXT NOT NULL,
    version             BIGINT NOT NULL DEFAULT 0,
    computed_at         TIMESTAMPTZ DEFAULT now()
);

-- One materialized row per scope. A partial unique index handles the cohort-wide
-- (class_group IS NULL) row, which a plain UNIQUE(assessment_id, class_group) would not
-- deduplicate on PostgreSQL (NULLs are distinct there).
CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_analytics_scope
    ON assessment_analytics (assessment_id, class_group)
    WHERE class_group IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_analytics_cohort
    ON assessment_analytics (assessment_id)
    WHERE class_group IS NULL;
CREATE INDEX IF NOT EXISTS ix_assessment_analytics_assessment
    ON assessment_analytics (assessment_id);
