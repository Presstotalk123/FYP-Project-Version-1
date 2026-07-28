-- Add per-lab toggle to hide correctness feedback from students on task submissions.
-- Off by default; existing rows unaffected.
ALTER TABLE labs ADD COLUMN IF NOT EXISTS hide_correctness INTEGER NOT NULL DEFAULT 0;
