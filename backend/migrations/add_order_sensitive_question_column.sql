-- Add per-question toggle for row-order-sensitive grading of SQL submissions.
-- When on, a student's rows must match the correct query's order (enforces ORDER BY).
-- Off by default; existing rows unaffected. Standard-mode questions only.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS order_sensitive INTEGER NOT NULL DEFAULT 0;
