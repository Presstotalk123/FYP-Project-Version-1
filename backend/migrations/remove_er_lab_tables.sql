-- Remove the ER lab feature.
--
-- ER labs were a second lab system running parallel to SQL/graph labs, with
-- their own tables rather than a lab_type on `labs`. Staff had no navigation
-- path to it, so it was smoke-tested once in June 2026 and then abandoned.
-- ERD now has a single surface: the question bank, which remains usable inside
-- assessments.
--
-- The ERD tutor keeps working and keeps every conversation and message; it only
-- loses its lab-context columns, which were nullable and only ever populated for
-- lab conversations. SQLite cannot DROP COLUMN while a foreign key or index
-- references it, so both tutor tables are rebuilt in place.

PRAGMA foreign_keys = OFF;

-- ---- erd_tutor_conversations: drop er_lab_question_id, session_id ----
CREATE TABLE erd_tutor_conversations_new (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    er_diagram_question_id INTEGER,
    context_type VARCHAR(20) NOT NULL,
    ibl_stage VARCHAR(40) NOT NULL,
    hint_level INTEGER NOT NULL,
    misconceptions TEXT,
    current_erd_model TEXT,
    last_submit_report TEXT,
    last_submit_score TEXT,
    last_query_summary TEXT,
    last_student_goal TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id),
    FOREIGN KEY(er_diagram_question_id) REFERENCES er_diagram_questions (id)
);

INSERT INTO erd_tutor_conversations_new
    (id, user_id, er_diagram_question_id, context_type, ibl_stage, hint_level,
     misconceptions, current_erd_model, last_submit_report, last_submit_score,
     last_query_summary, last_student_goal, created_at, updated_at)
SELECT id, user_id, er_diagram_question_id, context_type, ibl_stage, hint_level,
       misconceptions, current_erd_model, last_submit_report, last_submit_score,
       last_query_summary, last_student_goal, created_at, updated_at
FROM erd_tutor_conversations;

DROP TABLE erd_tutor_conversations;
ALTER TABLE erd_tutor_conversations_new RENAME TO erd_tutor_conversations;

CREATE INDEX ix_erd_tutor_conversations_id ON erd_tutor_conversations (id);
CREATE INDEX ix_erd_tutor_conversations_user_id ON erd_tutor_conversations (user_id);
CREATE INDEX ix_erd_tutor_conv_standalone ON erd_tutor_conversations (user_id, er_diagram_question_id);

-- ---- erd_tutor_messages: drop submission_id ----
CREATE TABLE erd_tutor_messages_new (
    id INTEGER NOT NULL,
    conversation_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    mode VARCHAR(10) NOT NULL,
    content TEXT,
    metadata_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY(conversation_id) REFERENCES erd_tutor_conversations (id)
);

INSERT INTO erd_tutor_messages_new
    (id, conversation_id, role, mode, content, metadata_json, created_at)
SELECT id, conversation_id, role, mode, content, metadata_json, created_at
FROM erd_tutor_messages;

DROP TABLE erd_tutor_messages;
ALTER TABLE erd_tutor_messages_new RENAME TO erd_tutor_messages;

CREATE INDEX ix_erd_tutor_messages_id ON erd_tutor_messages (id);
CREATE INDEX ix_erd_tutor_messages_conversation_id ON erd_tutor_messages (conversation_id);
CREATE INDEX ix_erd_tutor_msg_conv ON erd_tutor_messages (conversation_id, created_at);

-- ---- the ER lab tables themselves ----
DROP TABLE IF EXISTS er_lab_submissions;
DROP TABLE IF EXISTS er_lab_sessions;
DROP TABLE IF EXISTS er_lab_questions;
DROP TABLE IF EXISTS er_labs;

PRAGMA foreign_keys = ON;
