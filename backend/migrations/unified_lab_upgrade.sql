-- Unified-lab upgrade for an EXISTING Supabase/Postgres database that still has main's
-- single-database lab schema.
--
-- WHAT IT DOES
--   Drops the lab tables whose shape changed (and the now-removed ER-lab tables), so the
--   backend can rebuild them in the new pool-based shape on startup. KEEPS users,
--   questions, er_diagram_questions, whitelist_entries, attempts, and user_progress.
--
-- WHY (the root cause)
--   The app's startup runs SQLAlchemy create_all(), which only CREATES MISSING tables --
--   it never alters a table that already exists. main's `labs` table has NOT NULL columns
--   that were removed (schema_sql, sample_data_sql, template_db_path) and is missing the
--   new NOT NULL join_password_* columns, so inserting a unified lab fails until the table
--   is rebuilt. The single-DB lab data model changed to pool-based, so old lab rows cannot
--   be migrated meaningfully -- they are discarded.
--
-- HOW TO RUN
--   1. Take a backup / snapshot of the database first.
--   2. Run this whole file once against the database (Supabase SQL editor, or psql).
--   3. Restart the backend. On startup, create_all() recreates the dropped lab tables in
--      the new shape and creates the new tables (lab_items, lab_submissions, sql_lab_*,
--      graph_*); main.py then (re)asserts the active-session partial unique index.
--
-- NOTE
--   If, after restart, login or /problems fails with
--   "'STAFF' is not among the defined enum values", the users.role column holds legacy
--   uppercase enum NAMES; fix with:  UPDATE users SET role = lower(role);

BEGIN;

DROP TABLE IF EXISTS
    lab_submissions,
    lab_task_submissions,
    lab_tasks,
    lab_attempts,
    lab_items,
    lab_sessions,
    labs,
    er_lab_submissions,
    er_lab_sessions,
    er_lab_questions,
    er_labs
CASCADE;

COMMIT;
