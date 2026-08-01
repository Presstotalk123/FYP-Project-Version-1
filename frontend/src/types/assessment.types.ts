export type AssessmentItemType = 'sql_question' | 'er_question' | 'sql_lab' | 'graph_lab';

export interface AssessmentItemIn {
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
}

export interface AssessmentItemResponse {
  id: number;
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
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
}

export interface StudentAssessmentItemView {
  id: number;
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
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
  is_active: boolean;
  joined_at: string;
  submitted_at: string | null;
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
}

export interface StudentComponentScoresResponse {
  student_id: number;
  student_email: string;
  assessment_id: number;
  assessment_title: string;
  items: AssessmentItemComponentScore[];
}
