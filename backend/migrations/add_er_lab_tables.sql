-- ER lab feature: four tables.
-- Partial unique index for active sessions is dialect-specific and lives
-- in the runner script rather than this DDL file.

CREATE TABLE IF NOT EXISTS er_labs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    join_password_hash VARCHAR(255) NOT NULL,
    join_password_plain VARCHAR(255) NOT NULL,
    is_published INTEGER DEFAULT 0,
    is_running INTEGER DEFAULT 0,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER DEFAULT 0,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS er_lab_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    er_lab_id INTEGER NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    title VARCHAR(255) NOT NULL,
    problem_statement TEXT NOT NULL,
    notation VARCHAR(50) NOT NULL DEFAULT 'Chen',
    difficulty_label VARCHAR(20) NOT NULL,
    difficulty_rationale TEXT NOT NULL,
    rubric_md TEXT NOT NULL,
    rubric_json TEXT NOT NULL,
    instruction_history_json TEXT NOT NULL,
    model_answer_storage_key VARCHAR(500),
    model_answer_url VARCHAR(1000),
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER DEFAULT 0,
    CHECK (notation IN ('Chen')),
    CHECK (difficulty_label IN ('Easy','Medium','Hard')),
    FOREIGN KEY (er_lab_id) REFERENCES er_labs(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_er_lab_questions_lab_order ON er_lab_questions(er_lab_id, order_index);
CREATE INDEX IF NOT EXISTS ix_er_lab_questions_lab_deleted ON er_lab_questions(er_lab_id, is_deleted);

CREATE TABLE IF NOT EXISTS er_lab_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    er_lab_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    FOREIGN KEY (er_lab_id) REFERENCES er_labs(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_er_lab_sessions_lab_user ON er_lab_sessions(er_lab_id, user_id);
CREATE INDEX IF NOT EXISTS ix_er_lab_sessions_lab_active ON er_lab_sessions(er_lab_id, is_active);

CREATE TABLE IF NOT EXISTS er_lab_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    er_lab_question_id INTEGER NOT NULL,
    er_lab_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    submitted_xml TEXT,
    submitted_image_storage_key VARCHAR(500),
    auto_score_earned REAL NOT NULL,
    auto_score_total REAL NOT NULL,
    auto_score_percent REAL NOT NULL,
    auto_score_label VARCHAR(255) NOT NULL,
    auto_checks_json TEXT NOT NULL,
    auto_graded_at TIMESTAMP NOT NULL,
    override_score_earned REAL,
    override_score_total REAL,
    override_score_percent REAL,
    override_reason TEXT,
    overridden_by INTEGER,
    overridden_at TIMESTAMP,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (er_lab_question_id) REFERENCES er_lab_questions(id),
    FOREIGN KEY (er_lab_id) REFERENCES er_labs(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (session_id) REFERENCES er_lab_sessions(id),
    FOREIGN KEY (overridden_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_er_lab_submissions_question_user ON er_lab_submissions(er_lab_question_id, user_id);
CREATE INDEX IF NOT EXISTS ix_er_lab_submissions_user_lab ON er_lab_submissions(user_id, er_lab_id);
CREATE INDEX IF NOT EXISTS ix_er_lab_submissions_question_time ON er_lab_submissions(er_lab_question_id, submitted_at);
