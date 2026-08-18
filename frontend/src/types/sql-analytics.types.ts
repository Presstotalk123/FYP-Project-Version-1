export interface SqlStudentRollup {
  user_id: number;
  email: string;
  /** Display name from the user record; null when the student never set one. */
  name: string | null;
  class_group: string | null;
  attempts_count: number;
  completed: boolean;
  queries_to_correct: number | null;
  used_chatbot: boolean;
  last_attempted_at: string | null;
}

export interface SqlQuestionAnalytics {
  question_id: number;
  title: string;
  student_count: number;
  completed_count: number;
  avg_queries_to_correct: number | null;
  chatbot_student_count: number;
  students: SqlStudentRollup[];
}

export interface QueryHistoryRow {
  id: number;
  query: string;
  is_correct: boolean;
  error_message: string | null;
  execution_time_ms: number | null;
  submitted_at: string | null;
}

export interface ChatMessageRow {
  role: string;
  content: string;
  created_at: string | null;
}

export interface ReviewHistoryRow {
  id: number;
  student_query: string;
  problem_token: string | null;
  explanation: string | null;
  hint: string | null;
  created_at: string | null;
}

export interface SqlStudentDetail {
  student_id: number;
  query_history: QueryHistoryRow[];
  chatbot: ChatMessageRow[];
  review_history: ReviewHistoryRow[];
}
