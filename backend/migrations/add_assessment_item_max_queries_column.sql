-- Per-question max queries limit.
-- assessment_items.max_queries: cap on how many queries a student may run on this SQL
-- question during the assessment. NULL = unlimited (default / legacy behaviour). Only
-- meaningful for sql_question items; enforced at runtime in the execute endpoint.
ALTER TABLE assessment_items ADD COLUMN IF NOT EXISTS max_queries INTEGER;
