export type AssessmentItemType = 'sql_question' | 'er_question' | 'sql_lab' | 'graph_lab';

export interface AssessmentItemIn {
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
  weight: number;
  // Per-item override: when true, students see a neutral "Submitted" result instead of
  // Correct/Incorrect. Applies to sql_question / sql_lab / graph_lab; ignored for er_question.
  hide_correctness: boolean;
  // Per-item cap on how many queries a student may run on this SQL question; null = unlimited.
  // Only meaningful for sql_question items.
  max_queries?: number | null;
}

export interface AssessmentItemResponse {
  id: number;
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
  weight: number;
  hide_correctness: boolean;
  max_queries?: number | null;
  item_title: string;
}

export interface Assessment {
  id: number;
  title: string;
  description: string | null;
  is_published: boolean;
  is_running: boolean;
  item_count: number;
  has_password: boolean;
  time_limit_minutes: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface AssessmentDetail {
  id: number;
  title: string;
  description: string | null;
  is_published: boolean;
  is_running: boolean;
  items: AssessmentItemResponse[];
  created_by: number;
  password: string | null;
  has_password: boolean;
  time_limit_minutes: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface AssessmentCreate {
  title: string;
  description?: string;
  items: AssessmentItemIn[];
  password?: string;
  time_limit_minutes?: number | null;
}

export interface AssessmentUpdate {
  title?: string;
  description?: string;
  items?: AssessmentItemIn[];
  password?: string;
  clear_password?: boolean;
  time_limit_minutes?: number | null;
  clear_time_limit?: boolean;
}

// Student-side assessment types

export interface StudentAssessmentListItem {
  id: number;
  title: string;
  description: string | null;
  is_running: boolean;
  has_password: boolean;
  // True once this student has submitted this assessment (single-attempt).
  attempt_complete?: boolean;
  // Overall weighted score (0-100); null until staff release results (assessment stopped).
  weighted_score?: number | null;
  // When the student submitted; null if not yet completed. Used to order recent results.
  submitted_at?: string | null;
}

export interface StudentAssessmentItemView {
  id: number;
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
  weight: number;
  item_title: string;
  visited: boolean;
}

export interface StudentAssessmentDetail {
  id: number;
  title: string;
  description: string | null;
  is_running: boolean;
  has_password: boolean;
  // Optional whole-minute time limit; null = untimed. Shown on the Begin screen.
  time_limit_minutes: number | null;
  // True once this student has ended & submitted; UI shows a Completed state and
  // hides Join/Continue (assessments are single-attempt).
  attempt_complete: boolean;
  // Overall weighted score (0-100). Only set once staff have stopped the assessment
  // (results released); null while it is still running or when unweighted.
  weighted_score: number | null;
  items: StudentAssessmentItemView[];
}

export interface AssessmentSessionResponse {
  id: number;
  assessment_id: number;
  user_id: number;
  is_active: boolean;
  joined_at: string;
  submitted_at: string | null;
  // Deadline for this attempt (ISO); null = untimed. The countdown ticks toward this.
  end_time: string | null;
}

export interface ItemVisitResponse {
  session_id: number;
  assessment_item_id: number;
  first_visited_at: string;
}

export interface AssessmentStudentRow {
  user_id: number;
  email: string;
  // Optional lab/class group the student belongs to.
  class_group?: string | null;
  is_active: boolean;
  joined_at: string;
  submitted_at: string | null;
  // Weighted total (0-100) from the student's activity; null if the assessment is unweighted.
  weighted_score?: number | null;
}

export interface AssessmentStudentsResponse {
  assessment_id: number;
  assessment_title: string;
  students: AssessmentStudentRow[];
}

export interface AssessmentItemComponentScore {
  assessment_item_id: number;
  item_type: AssessmentItemType;
  item_id: number;
  item_title: string;
  order_index: number;
  has_correct_attempt?: boolean | null;
  attempt_count?: number | null;
  tasks_correct?: number | null;
  tasks_total?: number | null;
  visited?: boolean | null;
  weight?: number;
  score_fraction?: number | null;
  weighted_points?: number | null;
}

export interface StudentComponentScoresResponse {
  student_id: number;
  student_email: string;
  assessment_id: number;
  assessment_title: string;
  items: AssessmentItemComponentScore[];
  total_weighted_score?: number | null;
}
