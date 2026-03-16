-- Add unique constraint to prevent duplicate active sessions
-- This migration ensures only one active session per user+lab combination
-- Date: 2026-03-16
-- Purpose: Fix race condition in session creation

-- For SQLite: We need to recreate the table with the constraint
-- This migration is idempotent (safe to run multiple times)

-- Step 1: Create a temporary table with the new constraint
CREATE TABLE IF NOT EXISTS lab_sessions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    db_file_path VARCHAR(500) NOT NULL,
    is_active INTEGER DEFAULT 1,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    FOREIGN KEY (lab_id) REFERENCES labs(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (lab_id, user_id, is_active)
);

-- Step 2: Copy data from old table to new table
-- Using INSERT OR IGNORE to handle any existing duplicate data gracefully
INSERT OR IGNORE INTO lab_sessions_new
SELECT id, lab_id, user_id, db_file_path, is_active, started_at, ended_at
FROM lab_sessions;

-- Step 3: Drop old table
DROP TABLE lab_sessions;

-- Step 4: Rename new table to original name
ALTER TABLE lab_sessions_new RENAME TO lab_sessions;

-- Step 5: Recreate indexes
CREATE INDEX IF NOT EXISTS idx_lab_user ON lab_sessions(lab_id, user_id);
CREATE INDEX IF NOT EXISTS idx_active_sessions ON lab_sessions(lab_id, is_active);

-- Verification query (run manually after migration):
-- SELECT sql FROM sqlite_master WHERE type='table' AND name='lab_sessions';
-- Should show: UNIQUE (lab_id, user_id, is_active)
