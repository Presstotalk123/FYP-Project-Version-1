-- Migration: Add lab_tasks table for task management feature
-- Date: 2026-03-14
-- Description: Allows staff to create tasks for labs with hashed answers for validation

CREATE TABLE IF NOT EXISTS lab_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_id INTEGER NOT NULL,

    -- Task content
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,

    -- Answer validation (nullable - can be assigned later)
    correct_answer_hash VARCHAR(64) NULL,
    correct_query TEXT NULL,

    -- Ordering
    order_index INTEGER NOT NULL DEFAULT 0,

    -- Metadata
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Soft delete
    is_deleted INTEGER DEFAULT 0,

    -- Foreign keys
    FOREIGN KEY (lab_id) REFERENCES labs(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_lab_tasks_lab_id ON lab_tasks(lab_id);
CREATE INDEX IF NOT EXISTS idx_lab_tasks_lab_order ON lab_tasks(lab_id, order_index);
CREATE INDEX IF NOT EXISTS idx_lab_tasks_created_at ON lab_tasks(lab_id, created_at);
