-- Add lab_type column to labs table
-- Run against Supabase (PostgreSQL) once.
-- Existing rows default to 'sql' so no data migration is required.

ALTER TABLE labs ADD COLUMN IF NOT EXISTS lab_type VARCHAR(10) NOT NULL DEFAULT 'sql';
