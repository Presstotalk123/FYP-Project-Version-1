-- Add Advanced SQL Testing support to questions (triggers / complex DML grading).
-- Off by default; existing rows unaffected.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS advanced_sql_testing INTEGER NOT NULL DEFAULT 0;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS test_script TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS check_query TEXT;
