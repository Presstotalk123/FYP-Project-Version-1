export interface ExecuteRequest {
  question_id: number;
  query: string;
}

export interface ExecuteResponse {
  is_correct: boolean;
  execution_time_ms: number;
  results: Array<Record<string, any>>;
  columns: string[];
  error_message: string | null;
  row_count: number;
}

export interface Attempt {
  id: number;
  user_id: number;
  question_id: number;
  query: string;
  is_correct: boolean;
  execution_time_ms: number | null;
  error_message: string | null;
  submitted_at: string;
}

export interface AttemptHistory {
  id: number;
  question_id: number;
  question_title: string;
  query: string;
  is_correct: boolean;
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
