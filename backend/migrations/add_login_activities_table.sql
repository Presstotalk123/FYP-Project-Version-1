-- Migration: Add login_activities table for the student login-streak / activity-calendar feature.
-- One row per student per Singapore-calendar day on which they logged in.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS login_activities (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    login_date  DATE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT _user_login_date_uc UNIQUE (user_id, login_date)
);

CREATE INDEX IF NOT EXISTS ix_login_activities_user_id ON login_activities (user_id);
