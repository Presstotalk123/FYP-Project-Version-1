-- Add per-question toggle to hide correctness feedback from students on SQL submissions.
-- Off by default; existing rows unaffected. Mirrors labs.hide_correctness.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS hide_correctness INTEGER NOT NULL DEFAULT 0;
