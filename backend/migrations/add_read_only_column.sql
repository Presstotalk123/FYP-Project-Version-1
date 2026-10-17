-- Add per-lab read-only mode for SQL labs: students query the shared template
-- directly (opened read-only, read-only statements only) instead of a per-student copy.
-- Off by default; existing rows unaffected.
ALTER TABLE labs ADD COLUMN IF NOT EXISTS read_only INTEGER NOT NULL DEFAULT 0;
