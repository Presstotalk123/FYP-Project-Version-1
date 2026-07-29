-- Add per-lab toggle to turn off the AI Tutor chat tab and the AI query-review
-- hint for students, independent of hide_correctness.
-- Off by default; existing rows unaffected.
ALTER TABLE labs ADD COLUMN IF NOT EXISTS disable_ai_assist INTEGER NOT NULL DEFAULT 0;
