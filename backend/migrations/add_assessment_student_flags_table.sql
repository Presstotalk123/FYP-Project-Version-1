-- Staff flags on students, one row per (assessment, student).
-- Reference DDL for Postgres. run_assessment_student_flags_migration.py is the
-- script that actually runs. See HANDOFF.md section 8.
CREATE TABLE IF NOT EXISTS assessment_student_flags (
    id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    reason TEXT,
    flagged_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT uq_assessment_student_flag UNIQUE (assessment_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_assessment_student_flags_assessment_id
    ON assessment_student_flags (assessment_id);
