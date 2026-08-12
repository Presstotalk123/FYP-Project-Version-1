-- Timing Gateway: per-class-group scheduled access windows for assessments.
--
-- assessments.gateway_enabled: master toggle. When set, access is driven by the
--   per-class-group windows below (superseding the manual is_running start/stop).
-- assessment_sessions.hard_deadline: immovable class-group window end stamped at join;
--   the effective deadline is the earlier of end_time and hard_deadline (NULL = gateway off).
-- assessment_class_windows: one row per (assessment, class_group) with the UTC access window.

ALTER TABLE assessments ADD COLUMN IF NOT EXISTS gateway_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS hard_deadline TIMESTAMP NULL;

CREATE TABLE IF NOT EXISTS assessment_class_windows (
    id            SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    class_group   VARCHAR(100) NOT NULL,
    start_at      TIMESTAMP NOT NULL,
    end_at        TIMESTAMP NOT NULL,
    is_enabled    INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_assessment_class_window UNIQUE (assessment_id, class_group)
);

CREATE INDEX IF NOT EXISTS ix_assessment_class_windows_assessment
    ON assessment_class_windows (assessment_id, class_group);
