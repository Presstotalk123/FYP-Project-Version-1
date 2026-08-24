export type AnalyticsContext = "practice" | "assessment" | "all";

export interface CheckRate {
  id: string;
  dimension: string;
  requirement_level: string;
  pass_criteria: string;
  pass_rate: number;
  partial_rate: number;
  fail_rate: number;
  total: number;
}

export interface StudentRollup {
  user_id: number;
  email: string;
  /** Display name from the user record; null when the student never set one. */
  name: string | null;
  class_group: string | null;
  attempts: number;
  best_percent: number | null;
  latest_percent: number | null;
  last_attempt_at: string | null;
}

/** A bucket of what students asked Baloo about, with recent examples. */
export interface QueryTopic {
  topic: string;
  count: number;
  examples: string[];
}

export interface QuestionAnalytics {
  question_id: number;
  title: string;
  attempt_count: number;
  student_count: number;
  avg_percent: number | null;
  histogram: { bucket: number; count: number }[];
  checks: CheckRate[];
  students: StudentRollup[];
  /** Asked while working on this question, rather than across the whole cohort. */
  query_topics: QueryTopic[];
}

export interface AttemptSummary {
  id: number;
  created_at: string | null;
  percent: number | null;
  label: string | null;
  hint_level_at_submit: number | null;
  ibl_stage_at_submit: string | null;
  has_image: boolean;
  /** Non-null when a rubric regrade replaced this attempt's grade. */
  regraded_at: string | null;
}

export interface StudentSubmissions {
  student_id: number;
  attempts: AttemptSummary[];
  chat: { queries_asked: number; topics: string[] };
}

export interface SubmissionCheck {
  id: string;
  dimension?: string;
  requirement_level?: string;
  status: string;
  points?: number;
  /** Points awarded. Present on scoring checks; absent on ones excluded from the total. */
  earned_points?: number;
  brief_reason?: string;
  /** What the check tests, joined from the question's rubric — "A1" alone says nothing. */
  pass_criteria?: string;
}

/** Present only when staff have corrected the grade; null on an AI-graded attempt. */
export interface ScoreOverride {
  reason: string | null;
  by_user_id: number | null;
  by_email: string | null;
  at: string;
  original_score: {
    earned_points?: number;
    total_points?: number;
    percent?: number;
    label?: string;
  };
  original_checks: SubmissionCheck[];
}

/** What the server returns after a correction or a revert. */
export interface ScoreOverrideResult {
  score: {
    earned_points?: number;
    total_points?: number;
    percent?: number;
    label?: string;
  };
  checks: SubmissionCheck[];
  /** False when the attempt was not the student's latest, so only analytics moved. */
  assessment_mark_updated: boolean;
  override: ScoreOverride | null;
}

export interface SubmissionDetail {
  id: number;
  user_id: number;
  question_id: number;
  created_at: string | null;
  score_earned: number | null;
  score_total: number | null;
  score_percent: number | null;
  score_label: string | null;
  checks: SubmissionCheck[];
  override: ScoreOverride | null;
  /** Only the latest attempt carries the student's mark, so only it can move one. */
  is_latest_attempt: boolean;
  submission_description: string | null;
  submitted_xml: string | null;
  has_image: boolean;
  hint_level_at_submit: number | null;
  ibl_stage_at_submit: string | null;
  /** Non-null when a rubric regrade replaced this attempt's grade. */
  regraded_at: string | null;
}

export interface ClassOverview {
  dimensions: {
    dimension: string;
    fail_rate: number;
    partial_rate: number;
    checks_evaluated: number;
  }[];
  top_failing_checks: {
    question_id: number;
    question_title: string;
    check_id: string;
    dimension: string;
    fail_rate: number;
    attempts: number;
  }[];
  query_topics: QueryTopic[];
  questions: {
    question_id: number;
    title: string;
    attempts: number;
    students: number;
    avg_percent: number | null;
  }[];
}
