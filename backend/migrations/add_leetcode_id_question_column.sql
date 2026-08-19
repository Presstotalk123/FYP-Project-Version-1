-- Add the LeetCode problem number for questions imported from the LeetCode bank
-- (DATABASE_README_EN.md ordering). NULL for hand-authored / non-LeetCode questions.
-- Nullable, no default; existing rows keep NULL until backfilled.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS leetcode_id INTEGER;
