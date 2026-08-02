export interface ExecuteRequest {
  question_id: number;
  query: string;
}

export interface ExecuteResponse {
  // null when the question hides correctness from students — render a neutral "Submitted" state.
  is_correct: boolean | null;
  execution_time_ms: number;
  results: Array<Record<string, unknown>>;
  columns: string[];
  error_message: string | null;
  row_count: number;
  // Assessment deadline after crediting this query's time; null/undefined outside a timed
  // assessment. The countdown resumes from this without a separate session request.
  assessment_end_time?: string | null;
}

export interface Attempt {
  id: number;
  user_id: number;
  question_id: number;
  query: string;
  // null when the question hides correctness from students.
  is_correct: boolean | null;
  execution_time_ms: number | null;
  error_message: string | null;
  submitted_at: string;
}

export interface AttemptHistory {
  id: number;
  question_id: number;
  question_title: string;
  query: string;
  // null when the question hides correctness from students.
  is_correct: boolean | null;
  execution_time_ms: number | null;
  submitted_at: string;
}

export interface Progress {
  question_id: number;
  question_title: string;
  completed: boolean;
  attempts_count: number;
  last_attempted_at: string | null;
  first_completed_at: string | null;
}
