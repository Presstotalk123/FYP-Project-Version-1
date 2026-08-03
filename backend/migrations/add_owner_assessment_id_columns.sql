-- Isolate per-assessment progress by cloning content on publish.
-- owner_assessment_id marks a row as an assessment-owned clone (created at publish
-- time); NULL means it is a master bank row. Clones are excluded from bank listings.
-- source_item_id (on assessment_items) records the original master content id so a
-- re-publish is idempotent and unpublish can restore the master pointer.
-- All columns are nullable / additive; existing rows are unaffected.
ALTER TABLE questions            ADD COLUMN IF NOT EXISTS owner_assessment_id INTEGER NULL;
ALTER TABLE labs                 ADD COLUMN IF NOT EXISTS owner_assessment_id INTEGER NULL;
ALTER TABLE lab_tasks            ADD COLUMN IF NOT EXISTS owner_assessment_id INTEGER NULL;
ALTER TABLE er_diagram_questions ADD COLUMN IF NOT EXISTS owner_assessment_id INTEGER NULL;
ALTER TABLE assessment_items     ADD COLUMN IF NOT EXISTS source_item_id INTEGER NULL;

CREATE INDEX IF NOT EXISTS ix_questions_owner_assessment_id            ON questions(owner_assessment_id);
CREATE INDEX IF NOT EXISTS ix_labs_owner_assessment_id                ON labs(owner_assessment_id);
CREATE INDEX IF NOT EXISTS ix_lab_tasks_owner_assessment_id           ON lab_tasks(owner_assessment_id);
CREATE INDEX IF NOT EXISTS ix_er_diagram_questions_owner_assessment_id ON er_diagram_questions(owner_assessment_id);
