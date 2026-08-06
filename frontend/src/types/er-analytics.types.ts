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
  class_group: string | null;
  attempts: number;
  best_percent: number | null;
  latest_percent: number | null;
  last_attempt_at: string | null;
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
}

export interface AttemptSummary {
  id: number;
  created_at: string | null;
  percent: number | null;
  label: string | null;
  hint_level_at_submit: number | null;
  ibl_stage_at_submit: string | null;
  has_image: boolean;
}

export interface StudentSubmissions {
  student_id: number;
  attempts: AttemptSummary[];
  chat: { queries_asked: number; topics: string[] };
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
  checks: {
    id: string;
    dimension?: string;
    requirement_level?: string;
    status: string;
    points?: number;
    brief_reason?: string;
  }[];
  submission_description: string | null;
  submitted_xml: string | null;
  has_image: boolean;
  hint_level_at_submit: number | null;
  ibl_stage_at_submit: string | null;
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
  query_topics: { topic: string; count: number; examples: string[] }[];
  questions: {
    question_id: number;
    title: string;
    attempts: number;
    students: number;
    avg_percent: number | null;
  }[];
}
