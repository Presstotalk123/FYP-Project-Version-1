-- Add per-task toggle for row-order-sensitive grading of lab task submissions.
-- When on, a student's rows must match the correct query's order (enforces ORDER BY).
-- Off by default; existing rows unaffected.
ALTER TABLE lab_tasks ADD COLUMN IF NOT EXISTS order_sensitive INTEGER NOT NULL DEFAULT 0;
