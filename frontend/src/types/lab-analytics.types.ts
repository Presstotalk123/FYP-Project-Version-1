import type { ChatMessageRow } from "./sql-analytics.types";

export interface LabTaskStat {
  task_id: number;
  title: string;
  order_index: number;
  attempted_count: number;
  solved_count: number;
  avg_submissions_to_correct: number | null;
}

export interface LabStudentRollup {
  user_id: number;
  email: string;
  /** Display name from the user record; null when the student never set one. */
  name: string | null;
  class_group: string | null;
  tasks_correct: number;
  used_chatbot: boolean;
  last_submission_at: string | null;
}

export interface LabAnalytics {
  lab_id: number;
  title: string;
  total_tasks: number;
  student_count: number;
  chatbot_student_count: number;
  tasks: LabTaskStat[];
  students: LabStudentRollup[];
}

export interface LabQueryHistoryRow {
  id: number;
  query: string;
  success: boolean;
  error_message: string | null;
  execution_time_ms: number | null;
  row_count: number | null;
  session_id: number | null;
  submitted_at: string | null;
}

export interface LabReviewHistoryRow {
  id: number;
  task_id: number | null;
  student_query: string;
  problem_token: string | null;
  explanation: string | null;
  hint: string | null;
  db_state_message: string | null;
  created_at: string | null;
}

export interface LabStudentDetail {
  student_id: number;
  query_history: LabQueryHistoryRow[];
  chatbot: ChatMessageRow[];
  review_history: LabReviewHistoryRow[];
}
