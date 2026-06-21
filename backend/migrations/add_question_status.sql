-- Add draft/ready status to the two pool question types.
-- Existing rows were all created complete under the old atomic POST → backfill to 'ready'.
ALTER TABLE sql_lab_questions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'draft';
UPDATE  sql_lab_questions SET status = 'ready' WHERE is_deleted = 0;

ALTER TABLE graph_questions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'draft';
UPDATE  graph_questions SET status = 'ready' WHERE is_deleted = 0;
