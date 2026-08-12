-- Migration: Add platform_sessions table for the student platform-time-tracking feature.
-- One row per student login (session). A day's time on the platform is the SUM of that
-- day's sessions, where a session duration is (last_action_at - login_at).
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS platform_sessions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    login_date      DATE NOT NULL,
    login_at        TIMESTAMPTZ NOT NULL,
    last_action_at  TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_platform_sessions_user_id ON platform_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_platform_sessions_user_date ON platform_sessions (user_id, login_date);
