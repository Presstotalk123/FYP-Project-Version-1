-- Add per-assessment-item toggle to hide correctness feedback from students.
-- Off by default; existing rows unaffected. Written onto the content clone at publish
-- time (see assessment_clone). Applies to sql_question / sql_lab / graph_lab items.
ALTER TABLE assessment_items ADD COLUMN IF NOT EXISTS hide_correctness INTEGER NOT NULL DEFAULT 0;
