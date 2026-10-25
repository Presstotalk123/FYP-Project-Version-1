-- Per-assessment anti-cheat toggle: when on, SQL questions and SQL labs replace copied
-- text with an integrity notice and block pasting/dragging content in from outside.
-- On by default, so existing assessments keep the restrictions they already had.
ALTER TABLE assessments ADD COLUMN IF NOT EXISTS anti_cheat_enabled INTEGER NOT NULL DEFAULT 1;
