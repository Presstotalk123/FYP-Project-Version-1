-- Persist the SQL model answer so staff can edit existing SQL questions.
-- Safe for the existing PostgreSQL deployment: old rows remain NULL until edited.
ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS correct_answer_query TEXT;
