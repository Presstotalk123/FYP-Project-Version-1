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

/** One concept's cohort weakness: SQL has no rubric, so weakness is the share of
 *  attempted (student, tagged-question) pairs the student never completed. */
export interface SqlConceptWeakness {
  concept_id: number;
  slug: string;
  display_name: string;
  category: string;
  /** 0..1 — attempted pairs not completed / attempted pairs. Weakest first. */
  not_completed_rate: number;
  students: number;
  questions: number;
  /** Attempted (student, question) pairs the rate is computed over. */
  pairs: number;
}

export interface SqlOverviewQuestion {
  question_id: number;
  title: string;
  attempts: number;
  students: number;
  /** 0..1 — students who completed / students who attempted. */
  completion_rate: number;
}

export interface SqlClassOverview {
  concepts: SqlConceptWeakness[];
  questions: SqlOverviewQuestion[];
}

/** One student's SQL usage across every practice question. */
export interface SqlEngagementRow {
  user_id: number;
  email: string;
  name: string | null;
  class_group: string | null;
  practice_submissions: number;
  distinct_questions_tried: number;
  questions_completed: number;
  /** Questions completed / tried, as a percent; null if nothing tried. */
  completion_percent: number | null;
  chatbot_queries: number;
  first_activity_at: string | null;
}

export interface SqlEngagement {
  totals: {
    practice_submissions: number;
    students_engaged: number;
    registered_students: number;
    avg_completion_percent: number | null;
    chatbot_queries: number;
  };
  students: SqlEngagementRow[];
}
