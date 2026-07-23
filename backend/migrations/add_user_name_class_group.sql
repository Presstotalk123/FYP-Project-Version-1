-- Migration: Add name and class_group columns to users and whitelist_entries tables
-- These columns are optional (nullable) and default to NULL.

-- Users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255) DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS class_group VARCHAR(100) DEFAULT NULL;

-- Whitelist entries table (stores pre-login profile values)
ALTER TABLE whitelist_entries ADD COLUMN IF NOT EXISTS name VARCHAR(255) DEFAULT NULL;
ALTER TABLE whitelist_entries ADD COLUMN IF NOT EXISTS class_group VARCHAR(100) DEFAULT NULL;
