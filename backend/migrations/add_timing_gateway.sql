-- Timing Gateway: per-class-group scheduled access windows for assessments.
--
-- assessments.gateway_enabled: master toggle. When set, access is driven by the
--   per-class-group windows below (superseding the manual is_running start/stop).
-- assessment_sessions.hard_deadline: immovable class-group window end stamped at join;
--   the effective deadline is the earlier of end_time and hard_deadline (NULL = gateway off).
-- assessment_class_windows: one row per (assessment, class_group) with the UTC access window.
--
-- All timestamp columns are TIMESTAMPTZ (timestamp with time zone), matching every other
-- timing column in the schema (assessment_sessions.end_time/joined_at/submitted_at). An
-- earlier version of this migration used plain TIMESTAMP (without time zone) here, which
-- Postgres stores/returns as a naive datetime; the API then serialized it with no UTC
-- offset, and browsers parsed it as *local* time instead of UTC — shifting the deadline by
-- the viewer's UTC offset and causing spurious immediate auto-submits for anyone not in
-- UTC+0. The ALTER COLUMN block below corrects any database already migrated with that bug
-- (USING ... AT TIME ZONE 'UTC' reinterprets the existing naive digits as UTC, which is what
-- they always represented, rather than converting/shifting them).

ALTER TABLE assessments ADD COLUMN IF NOT EXISTS gateway_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS hard_deadline TIMESTAMPTZ NULL;

CREATE TABLE IF NOT EXISTS assessment_class_windows (
    id            SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    class_group   VARCHAR(100) NOT NULL,
    start_at      TIMESTAMPTZ NOT NULL,
    end_at        TIMESTAMPTZ NOT NULL,
    is_enabled    INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_assessment_class_window UNIQUE (assessment_id, class_group)
);

CREATE INDEX IF NOT EXISTS ix_assessment_class_windows_assessment
    ON assessment_class_windows (assessment_id, class_group);

-- Corrective step: if any of the three columns above were already created as plain
-- TIMESTAMP (no time zone) by an earlier run of this migration, convert them to
-- TIMESTAMPTZ, treating the existing naive values as UTC (they always were UTC digits,
-- just untagged). No-op (and safe to re-run) once the columns are already TIMESTAMPTZ.
DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'assessment_sessions' AND column_name = 'hard_deadline') = 'timestamp without time zone' THEN
        ALTER TABLE assessment_sessions
            ALTER COLUMN hard_deadline TYPE TIMESTAMPTZ USING hard_deadline AT TIME ZONE 'UTC';
    END IF;

    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'assessment_class_windows' AND column_name = 'start_at') = 'timestamp without time zone' THEN
        ALTER TABLE assessment_class_windows
            ALTER COLUMN start_at TYPE TIMESTAMPTZ USING start_at AT TIME ZONE 'UTC';
    END IF;

    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'assessment_class_windows' AND column_name = 'end_at') = 'timestamp without time zone' THEN
        ALTER TABLE assessment_class_windows
            ALTER COLUMN end_at TYPE TIMESTAMPTZ USING end_at AT TIME ZONE 'UTC';
    END IF;
END $$;
