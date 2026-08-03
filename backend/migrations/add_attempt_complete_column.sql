-- Single-attempt assessments: mark a session complete once the student ends & submits,
-- so re-joining/retaking is blocked. Additive; existing sessions default to 0 (not
-- complete) so in-progress/legacy sessions are not retroactively locked.
ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS attempt_complete INTEGER NOT NULL DEFAULT 0;
