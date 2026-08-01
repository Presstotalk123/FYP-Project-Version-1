-- Configurable assessment timer.
-- assessments.time_limit_minutes: optional whole-minute limit (NULL = untimed, unchanged behaviour).
-- assessment_sessions.end_time: per-student deadline (join time + limit, credited forward by query
-- execution time). NULL = untimed attempt. Backend source of truth for lazy expiration.
ALTER TABLE assessments ADD COLUMN IF NOT EXISTS time_limit_minutes INTEGER NULL;
ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS end_time TIMESTAMP NULL;
